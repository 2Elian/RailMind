from typing import Dict, Any, List
from datetime import datetime
import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from railmind.agent.state import AgentState
from railmind.operators.query_rewriter import QueryRewriter
from railmind.operators.intent_recognizer import IntentRecognizer
from railmind.operators.result_evaluator import ResultEvaluator
from railmind.operators.memory import get_memory_store
from railmind.function_call.kg_tools import TOOLS
from railmind.config import get_settings
from railmind.operators.templates.think import SYSTEM_PROMPT, USER_PROMPT
from railmind.operators.logger import get_logger
from railmind.agent.base_agent import BaseAgent
from railmind.utils import is_think_model, log_execution_time, parse_think_content
from railmind.operators.templates.answer_generate import FIN_SYSTEM_PROMPT, FIN_USER_PROMPT

class ReActAgent(BaseAgent):
    def __init__(self, error_backtracking_log_path: str = "/data/lzm/AgentDev/RailMind/data"):
        super().__init__(error_backtracking_log_path=error_backtracking_log_path)
        self.logger = get_logger(name='ReActAgent')
        settings = get_settings()
        # LLM for ReAct reasoning
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_api_base,
            temperature=0.2
        )
        self.query_rewriter = QueryRewriter(llm_instance=self.llm)
        self.intent_recognizer = IntentRecognizer(llm_instance=self.llm)
        self.result_evaluator = ResultEvaluator(llm_instance=self.llm)
        self.memory_store = get_memory_store()
        self.tools = {tool.name: tool for tool in TOOLS}
        self.graph = self._build_graph()
    
    def _func_logger(self, name):
        return get_logger(name=name)
    
    def _build_graph(self) -> StateGraph:
        """build LangGraph workflow"""
        workflow = StateGraph(AgentState)
        
        # add node
        workflow.add_node("init", self._init_state)
        workflow.add_node("rewrite_query", self._rewrite_query)
        workflow.add_node("recognize_intent", self._recognize_intent)
        workflow.add_node("react_think", self._react_think)
        workflow.add_node("execute_action", self._execute_action)
        workflow.add_node("evaluate_result", self._evaluate_result)
        workflow.add_node("generate_answer", self._generate_answer)
        
        # set a start
        workflow.set_entry_point("init")
        
        # add edge
        workflow.add_edge("init", "rewrite_query")
        workflow.add_edge("rewrite_query", "recognize_intent")
        workflow.add_edge("recognize_intent", "react_think")
        workflow.add_edge("react_think", "execute_action")
        workflow.add_edge("execute_action", "evaluate_result")
        
        # Conditional edge, determining whether to continue the loop.
        workflow.add_conditional_edges(
            "evaluate_result",
            self._should_continue,
            {
                "continue": "react_think",
                "finish": "generate_answer"
            }
        )
        
        workflow.add_edge("generate_answer", END)
        
        return workflow.compile(debug=False)
    
    async def _init_state(self, state: AgentState) -> AgentState:
        state["thoughts"] = []
        state["actions"] = []
        state["observations"] = []
        state["executed_functions"] = []
        state["accumulated_results"] = []
        state["iteration_count"] = 0
        state["max_iterations"] = 10
        state["start_time"] = datetime.now().isoformat()
        state["should_continue"] = True
        state["error"] = None
        state["last_error"] = None
        if "sub_queries" not in state:
            state["sub_queries"] = []
        state["current_sub_query_index"] = 0
        state["current_sub_query"] = {}
        state["current_functions"] = []
        state["current_entities"] = []
        state["current_intent"] = ""
        
        # load memory context
        state["memory_context"] = self.memory_store.get_session_context(
            state["session_id"]
        )
        return state
    
    
    @log_execution_time("Rewrite Query")
    async def _rewrite_query(self, state: AgentState) -> AgentState:
        # TODO 重写query是因为 用户输入的query不规范 --> 那如果用户输入的query非常规范，仍然进行query重写 会浪费时间！如何解决呢？
        try:
            result = await self.query_rewriter.rewrite(
                state["original_query"],
                context=state["memory_context"]
            )
            
            state["query_rewrite_result"] = result
            state["rewritten_query"] = result.get("rewritten_query", state["original_query"])
            
        except Exception as e:
            state["error"] = f"Query改写失败: {str(e)}"
            state["rewritten_query"] = state["original_query"]
            self.write_backtrack(error_msg=e, data=state)
        return state
    
    @log_execution_time("Intent Recognize")
    async def _recognize_intent(self, state: AgentState) -> AgentState:
        # 多个意图识别的不好！请问明天北京去西安的列车都有哪些？上午8点之前发车的呢？这是两个query！但是系统判断为了一个query
        try:
            result = await self.intent_recognizer.recognize(state["rewritten_query"])
            state["intent_result"] = result
            for i, q in zip(result.get("intents", []), result.get("queries", [])):
                state["sub_queries"].append({
                    "sub_query": q["sub_query"],
                    "type": i["type"],
                    "description": i["description"],
                    "confidence": i["confidence"], 
                    "entities": q.get("entities", []),
                    "relevant_functions": q.get("relevant_functions", []),
                    "intent_index": q["intent_index"],
                    "results": []
                })
            
        except Exception as e:
            state["error"] = f"意图识别失败: {str(e)}"
            self.write_backtrack(error_msg=e, data=state)
        return state
    
    @log_execution_time("ReAct Think")
    async def _react_think(self, state: AgentState) -> AgentState:
        # V0.1版本 先按intent_index执行 --> 每一个子查询的执行均与其他查询相关 做了一个完全的历史上下文信息
        # V0.2后续改进： 先判断所有子查询的依存关系 进行分组，独立的子查询并发执行，有依存关系的子查询需要按步骤执行。
        # V0.3: func 召回问题 func召回的不准 后面会多走很多的loop 浪费时间
        # V0.4Agent-Memory板块 做推理路径的缓存 比如用户1第一次的推理路径是 A-> B -> C -> D，第二次的查询类似，就可以复用一部分路径 节省时间
        self._update_current_sub_query(state)
        try:
            if state["sub_queries"]:
                current_query = state["current_sub_query"].get("sub_query", state["rewritten_query"])
                current_entities = state["current_entities"]
                current_functions = state["current_functions"]
                current_intent = state["current_intent"]
            else:
                self.write_backtrack(error_msg="No Subquery Information Received", data=state)
                raise ValueError
            think_prompt = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT),
                ('user', USER_PROMPT)
            ])
            
            # 格式化function call 得到所有可用的func call
            func_schemas = self.intent_recognizer.get_function_schemas(current_functions)
            func_info = json.dumps(func_schemas, ensure_ascii=False, indent=2)
            exec_func_info = json.dumps(state["executed_functions"], ensure_ascii=False, indent=2)
            results_info = json.dumps(state["accumulated_results"][-3:], ensure_ascii=False, indent=2)
            
            # 构建子查询上下文
            sub_query_context = ""
            total = len(state["sub_queries"])
            current_idx = state["current_sub_query_index"]
            sub_query_context = f"当前正在处理第 {current_idx + 1}/{total} 个子查询。"
            self.logger.info(sub_query_context)

            # 添加前面子查询的结果作为上下文
            prev_results = []
            for i in range(current_idx):
                sq = state["sub_queries"][i]
                if sq.get("results"):
                    prev_results.append({
                        "sub_query": sq["sub_query"],
                        "results": sq["results"]
                    })
            
            if prev_results:
                sub_query_context += f"\n\n前面子查询的结果：\n{json.dumps(prev_results, ensure_ascii=False, indent=2)}"
            # 构建错误上下文 --> 模型给出的参数错误的case
            error_context = ""
            if "last_error" in state and state["last_error"]:
                last_error = state["last_error"]
                if last_error.get("error") == "missing_required_parameters":
                    error_context = f"""\n **上次执行失败**:
                    {last_error.get('message', '')}
                    缺少参数：{', '.join(last_error.get('required_params', []))}
                    {last_error.get('hint', '')}
                    请修正上次的函数调用，补充完整的参数。"""
                    # 清除错误标记 --> 避免重复提示
                    state["last_error"] = None

            chain = think_prompt | self.llm
            response = await chain.ainvoke({
                "available_functions": func_info,
                "query": current_query + sub_query_context,
                "intent": current_intent,
                "entities": json.dumps(current_entities, ensure_ascii=False),
                "executed_functions": exec_func_info,
                "current_results": results_info,
                "error_context": error_context
            })
            is_think = is_think_model(self.llm.model_name)
            # 解析思考结果
            try:
                if is_think:
                    _, res_context = parse_think_content(response.content)
                    thought_result = json.loads(res_context)
                else:
                    thought_result = json.loads(response.content)
            except:
                thought_result = {
                    "thought": response.content,
                    "reasoning": "无法解析 JSON",
                    "next_action": {
                        "function_name": current_functions[0] if current_functions else "search_entity",
                        "parameters": {},
                        "reason": "默认行动"
                    },
                    "expected_outcome": ""
                }
            
            # 记录 Thought
            state["thoughts"].append({
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "sub_query_index": state["current_sub_query_index"],
                "sub_query": current_query,
                "content": thought_result
            })
            
            # 记录 Action
            state["actions"].append({
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "sub_query_index": state["current_sub_query_index"],
                "action": thought_result.get("next_action", {})
            })
            
        except Exception as e:
            state["error"] = f"ReAct 思考失败: {str(e)}"
            state["actions"].append({
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "sub_query_index": state.get("current_sub_query_index", 0),
                "action": {
                    "function_name": "search_entity",
                    "parameters": {},
                    "reason": "异常恢复"
                }
            })
            self.write_backtrack(error_msg=e, data=state)
        return state
    
    @log_execution_time("Execute Action")
    async def _execute_action(self, state: AgentState) -> AgentState:
        # TODO 1. 高并发场景下 如何确保数据同步安全？
        # TODO 2. 如何保证多站点问题的模糊和确定性呢？ 比如用户模糊的查询是北京 那如何检索到 北京西、北京、北京南等站点呢？ 再比如用户精确查询 北京站 --> 但是数据库里面只有北京、北京西，怎么办呢？
        """
        TODO2 的真实badcase案例：
        案例1：
            Query：从北京西到西安的车次有哪些？
            召回func：find_trains_between_stations
            参数：{'departure_station': '北京西站', 'arrival_station': '西安站'}

            实际上应该是 北京西 西安，不能有站
        案例2：
            Query：从北京到西安的车次有哪些？
            实际上，我们数据库里面只有北京西，你搜北京、北京站 一定搜不到结果
        """
        try:
            if not state["actions"]:
                state["error"] = "没有可执行的 Action"
                return state
            
            current_action = state["actions"][-1]["action"]
            func_name = current_action.get("function_name")
            params = current_action.get("parameters", {})
            result = await self._call_function(func_name, params, state)
            # 埋点: 收集badcase
            if not result:
                bad_case_data = {
                    "func_name": func_name,
                    "params": params,
                    "state_snapshot": {
                        "query": state.get("original_query"),
                        "iteration": state.get("iteration_count")
                    }
                }
                self.write_backtrack(error_msg="Func Call执行返回结果为空", data=bad_case_data)
            # 记录 Observation
            observation = {
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "function": func_name,
                "parameters": params,
                "result": result,
                "result_summary": self._summarize_result(result)
            }
            
            state["observations"].append(observation)
            state["executed_functions"].append({
                "name": func_name,
                "parameters": params,
                "result_summary": observation["result_summary"]
            })
            is_param_error = isinstance(result, dict) and result.get("error") == "missing_required_parameters"
            end_signals = ["end_of_turn", "end_task", "finish", "complete", "none", "null", "None"]
            is_end_signal = func_name in end_signals or not func_name
            if result and not is_param_error and not is_end_signal:
                if not (isinstance(result, dict) and "error" in result):
                    state["accumulated_results"].extend(result if isinstance(result, list) else [result])
            if is_end_signal:
                self.logger.info(f"模型调用 {func_name}，当前子查询完成")
                state["should_continue"] = False
            # 如果是参数缺失错误，记录到 state 以便 rethink
            if is_param_error:
                state["last_error"] = result
                self.logger.warning(f"参数缺失: {result.get('message')}")
            
        except Exception as e:
            state["error"] = f"执行 Action 失败: {str(e)}"
            state["observations"].append({
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            self.write_backtrack(error_msg=f"执行 Action 失败: {str(e)}", data={
                    "error_type": type(e).__name__,
                    "func_name": current_action.get("function_name") if 'current_action' in locals() else "unknown",
                    "iteration": state.get("iteration_count", 0)
                })
        return state
    
    @log_execution_time("Evaluate Result")
    async def _evaluate_result(self, state: AgentState) -> AgentState:
        # TODO: 如果是数据本身原因/我们系统100%无法解决的问题 该如何做出判断呢？比如：用户查询北京西到西安早上8点前的列车，但是我们数据库里面早上8点前的时间数据 都是nan 这样就会导致数据库cypher查询结果为空 loop=True无线循环
        try:
            state["iteration_count"] += 1
            if state["iteration_count"] >= state["max_iterations"]:
                self.logger.warning(f"达到最大迭代次数 {state['max_iterations']}，强制停止")
                self.write_backtrack(error_msg=f"达到最大迭代次数 {state['max_iterations']}，强制停止",
                                     data=state)
                state["should_continue"] = False
                state["evaluation_result"] = {
                    "should_continue": False,
                    "reason": "达到最大迭代次数"
                }
                return state
            if state.get("error"):
                self.logger.warning(f"检测到错误，停止执行: {state['error']}")
                self.write_backtrack(error_msg=f"检测到错误，停止执行: {state['error']}",
                                     data=state)
                state["should_continue"] = False
                return state
            
            """
            下面的代码目的是为了：
            1. 避免无意义的评估
            2. 节省 LLM 调用成本
            3. 提高响应速度
            
            # 情况 1: 没有结果或结果太少
            accumulated_results = []  # 或者很少的内容
            quick_check() → False
            not False → True
            → 进入分支：should_continue = True，继续执行
            → 跳过后面的详细评估（因为还没收集到足够信息）
            → 重回rethink

            # 情况 2: 有足够的结果
            accumulated_results = [result1, result2, ...]
            quick_check() → True
            not True → False
            → 不进入分支
            → 继续执行后面的详细评估逻辑
            """
            if not self.result_evaluator.quick_check(state["accumulated_results"]):
                state["should_continue"] = True
                return state

            if state["sub_queries"]:
                current_idx = state["current_sub_query_index"]
                current_sq = state["sub_queries"][current_idx] if current_idx < len(state["sub_queries"]) else None
                
                if current_sq:
                    # 评估当前子查询是否完成
                    sq_eval_result = await self.result_evaluator.evaluate(
                        current_sq["sub_query"],
                        state["executed_functions"],
                        current_sq.get("results", [])
                    )
                    # 如果当前子查询完成，切换到下一个
                    if not sq_eval_result.get("should_continue", True):
                        self.logger.info(f"子查询 {current_idx + 1} 完成")
                        state["current_sub_query_index"] += 1
                        
                        # 检查是否所有子查询都完成
                        if state["current_sub_query_index"] >= len(state["sub_queries"]):
                            state["should_continue"] = False
                            state["evaluation_result"] = {
                                "should_continue": False,
                                "reason": "所有子查询已完成"
                            }
                        else:
                            # 还有子查询，继续处理
                            state["should_continue"] = True
                            state["evaluation_result"] = {
                                "should_continue": True,
                                "reason": f"继续处理子查询 {state['current_sub_query_index'] + 1}"
                            }
                    else:
                        # 当前子查询未完成，继续处理
                        state["should_continue"] = True
                        state["evaluation_result"] = sq_eval_result
                else:
                    # 没有更多子查询
                    state["should_continue"] = False
                    state["evaluation_result"] = {
                        "should_continue": False,
                        "reason": "没有更多子查询"
                    }
            else:
                # 无子查询，使用整体评估
                eval_result = self.result_evaluator.evaluate(
                    state["rewritten_query"],
                    state["executed_functions"],
                    state["accumulated_results"]
                )
                
                state["evaluation_result"] = eval_result
                state["should_continue"] = eval_result.get("should_continue", False)
            
        except Exception as e:
            state["error"] = f"评估结果失败: {str(e)}"
            state["should_continue"] = False
            self.write_backtrack(error_msg=e, data=state)
        return state
    
    @log_execution_time("Generate Answer")
    async def _generate_answer(self, state: AgentState) -> AgentState:
        try:
            answer_prompt = ChatPromptTemplate.from_messages([
                ("system", FIN_SYSTEM_PROMPT),
                ("user", FIN_USER_PROMPT)
            ])
            results_str = json.dumps(state["accumulated_results"], ensure_ascii=False, indent=2)
            process_steps = []
            for i, (thought, action, obs) in enumerate(zip(
                state["thoughts"],
                state["actions"],
                state["observations"]
            )):
                process_steps.append(
                    f"步骤 {i+1}:\n"
                    f"  思考: {thought['content'].get('thought', '')}\n"
                    f"  行动: {action['action'].get('function_name', '')}\n"
                    f"  观察: {obs.get('result_summary', '')}"
                )
            process_str = "\n\n".join(process_steps)
            
            chain = answer_prompt | self.llm
            response = await chain.ainvoke({
                "query": state["original_query"],
                "results": results_str,
                "process": process_str
            })
            
            state["final_answer"] = response.content
            state["final_answer_metadata"] = {
                "total_iterations": state["iteration_count"],
                "functions_used": len(state["executed_functions"]),
                "results_count": len(state["accumulated_results"])
            }
            # TODO 存到短期 中期 还是长期?
            self.memory_store.add_to_short_term(state["session_id"], {
                "query": state["original_query"],
                "answer": state["final_answer"],
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            state["error"] = f"生成答案失败: {str(e)}"
            state["final_answer"] = "抱歉，无法生成答案。"
            self.write_backtrack(error_msg=e, data=state)
        return state
    
    def _update_current_sub_query(self, state: AgentState) -> None:
        """更新当前处理的子查询"""
        if not state["sub_queries"]:
            return
        current_idx = state["current_sub_query_index"]
        if current_idx < len(state["sub_queries"]):
            state["current_sub_query"] = state["sub_queries"][current_idx]
            state["current_entities"] = state["current_sub_query"].get("entities", [])
            state["current_functions"] = [
                f["function_name"] for f in state["current_sub_query"].get("relevant_functions", [])
            ]
            state["current_intent"] = state["current_sub_query"].get("type", '') + ": " + state["current_sub_query"].get("description", "")
        else:
            state["current_sub_query"] = {}
            state["current_entities"] = []
            state["current_functions"] = []
            state["current_intent"] = ""

    def _should_continue(self, state: AgentState) -> str:
        """判断是否继续 ReAct 循环"""
        if state.get("error"):
            return "finish"
        if not state.get("should_continue", False):
            return "finish"
        return "continue"
    
    async def _call_function(self, func_name: str, params: Dict[str, Any], state: AgentState) -> Any:
        """调用func call"""
        end_signals = ["end_of_turn", "end_task", "finish", "complete", "none", "null", "None"]
        if func_name in end_signals or not func_name:
            self.logger.info(f"模型调用 {func_name or 'empty'}，任务已完成")
            return {"message": "任务完成"}
        
        if func_name not in self.tools:
            self.write_backtrack(error_msg="未知函数名称", data={"error": f"未知函数: {func_name}"})
            raise ValueError
        
        tool = self.tools[func_name]
        required_params = self._get_required_params(tool)
        if not params:
            if not required_params:
                try:
                    result_str = await tool.ainvoke({})
                    return json.loads(result_str)
                except Exception as e:
                    return {"error": f"函数执行失败: {str(e)}"}
            if not self._validate_required_params(params, required_params):
                missing_params = [p for p in required_params if p not in params]
                # TODO 返回ReThink 告知模型 你缺少了参数
                self.write_backtrack(error_msg="missing_required_parameters", data=f"函数 {func_name} 所需要的参数为: {required_params}, 缺少必须参数: {', '.join(missing_params)}")
                return {
                    "error": "missing_required_parameters",
                    "message": f"函数 {func_name} 缺少必须参数: {', '.join(missing_params)}",
                    "required_params": required_params,
                    "hint": "请在下一次 Thought 中明确指定这些参数"
                }
        
        try:
            result_str = await tool.ainvoke(params)
            return json.loads(result_str)
        except Exception as e:
            error_msg = f"函数执行失败: {str(e)}"
            self.write_backtrack(error_msg=error_msg, data={
                    "func_name": func_name,
                    "params": params,
                    "error_type": type(e).__name__
                })
            return {"error": error_msg}
    
    def _summarize_result(self, result: Any) -> str:
        """总结函数执行结果"""
        if not result:
            return "无结果"
        if isinstance(result, list):
            return f"返回 {len(result)} 条记录"
        elif isinstance(result, dict):
            return f"返回字典，包含 {len(result)} 个字段"
        else:
            return str(result)[:100]
        
    def _get_required_params(self, tool) -> List[str]:
        """获取函数的必须参数列表"""
        required = []
        try:
            if hasattr(tool, 'args') and hasattr(tool.args, '__annotations__'):
                import inspect
                sig = inspect.signature(tool.func)
                for param_name, param in sig.parameters.items():
                    # 如果没有默认值，则为必须参数
                    if param.default == inspect.Parameter.empty and param_name != 'self':
                        required.append(param_name)
        except Exception:
            pass
        return required
    
    def _validate_required_params(self, params: Dict[str, Any], required_params: List[str]) -> bool:
        """验证是否提供了所有必须参数"""
        for param in required_params:
            if param not in params or params[param] is None:
                return False
        return True
    
    async def run(self, query: str, user_id: str, session_id: str) -> Dict[str, Any]:
        initial_state: AgentState = {
            "original_query": query,
            "user_id": user_id,
            "session_id": session_id,
            "rewritten_query": "",
            "query_rewrite_result": {},
            "intent_result": {},
            "entities": [],
            "relevant_functions": [],
            "sub_queries": [],
            "current_sub_query_index": 0,
            "current_sub_query": {},
            "current_functions": [],
            "current_entities": [],
            "current_intent": '',
            "thoughts": [],
            "actions": [],
            "observations": [],
            "executed_functions": [],
            "accumulated_results": [],
            "evaluation_result": {},
            "should_continue": True,
            "memory_context": {},
            "final_answer": "",
            "final_answer_metadata": {},
            "iteration_count": 0,
            "max_iterations": 10,
            "start_time": "",
            "error": None,
            "last_error": None
        }
        # LangGraph默认递归限制是 25
        try:
            final_state = await self.graph.ainvoke(
                initial_state,
                config={"recursion_limit": 30} # TODO 在配置文件里面写吧
            )
        except RecursionError as e:
            self.logger.error(f"递归限制错误: {str(e)}")
            return {
                **initial_state,
                "error": f"达到递归限制，系统强制停止: {str(e)}",
                "final_answer": "抱歉，系统处理超时。请简化您的问题后重试。"
            }
        
        return final_state