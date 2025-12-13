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
from railmind.agent.state import ErrorType

class ReActAgent(BaseAgent):
    def __init__(self, error_backtracking_log_path: str = "/data/lzm/AgentDev/RailMind/data"):
        super().__init__(error_backtracking_log_path=error_backtracking_log_path)
        self.logger = get_logger(name='ReActAgent')
        self.settings = get_settings()
        # LLM for ReAct reasoning
        self.llm = ChatOpenAI(
            model=self.settings.openai_model,
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_api_base,
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
                "finish": "generate_answer",
            }
        )
        workflow.add_conditional_edges(
            "execute_action",
            self._check_func_continue,
            {
                "continue": "evaluate_result",
                "finish": "generate_answer",
            }
        )
        # error conditional edge
        workflow.add_conditional_edges(
            "rewrite_query",
            self._check_error_or_continue,
            {
                "error": "generate_answer",
                "continue": "recognize_intent"
            }
        )
        workflow.add_conditional_edges(
            "recognize_intent",
            self._check_error_or_continue,
            {
                "error": "generate_answer",
                "continue": "react_think"
            }
        )
        workflow.add_conditional_edges(
            "react_think",
            self._check_error_or_continue,
            {
                "error": "generate_answer",
                "continue": "execute_action"
            }
        )
        workflow.add_conditional_edges(
            "execute_action",
            self._check_error_or_continue,
            {
                "error": "generate_answer",
                "continue": "evaluate_result"
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
        state["should_continue"] = False
        state["func_end"] = False
        state["error"] = None
        state["sub_queries"] = []
        state["rewritten_query"] = ""
        state["current_sub_query_index"] = 0
        state["current_sub_query"] = {}
        state["current_functions"] = []
        state["current_entities"] = []
        state["current_intent"] = ""
        state["current_result"] = []
        state["_previous_sub_query_index"] = -1
        state["total_iteration_count"] = 0
        state["param_error"] = None

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
            state["rewritten_query"] = result.get("rewritten_query", state["original_query"])
            
        except Exception as e:
            state["error"] = ErrorType.RW
            error_data = {
                "original_query": state["original_query"],
                "result": result
            }
            await self.write_backtrack(error_type=ErrorType.RW, error_msg=e, data=error_data)
        return state
    
    @log_execution_time("Intent Recognize")
    async def _recognize_intent(self, state: AgentState) -> AgentState:
        # TODO 多个意图识别的不好！请问明天北京去西安的列车都有哪些？上午8点之前发车的呢？这是两个query！但是系统判断为了一个query
        if state.get("error"):
            self.logger.info(f"An error {state['error']} was detected; skip intent_recognize.")
            return state
        try:
            result = await self.intent_recognizer.recognize(state["rewritten_query"])
            for i, q in zip(result.get("intents", []), result.get("queries", [])):
                state["sub_queries"].append({
                    "sub_query": q["sub_query"],
                    "type": i["type"],
                    "description": i["description"],
                    "confidence": i["confidence"], 
                    "entities": q.get("entities", []),
                    "relevant_functions": q.get("relevant_functions", []),
                    "intent_index": q["intent_index"],
                    "results": [],
                    "exe_process_data": {}
                })
            
        except Exception as e:
            state["error"] = ErrorType.IR
            error_data = {
                "original_query": state["original_query"],
                "result": result
            }
            await self.write_backtrack(error_type=ErrorType.IR, error_msg=e, data=error_data)
        return state
    
    @log_execution_time("ReAct Think")
    async def _react_think(self, state: AgentState) -> AgentState:
        # V0.1版本 先按intent_index执行 --> 每一个子查询的执行均与其他查询相关 做了一个完全的历史上下文信息
        # V0.2后续改进： 先判断所有子查询的依存关系 进行分组，独立的子查询并发执行，有依存关系的子查询需要按步骤执行。
        # V0.3: func 召回问题 func召回的不准 后面会多走很多的loop 浪费时间
        # V0.4Agent-Memory板块 做推理路径的缓存 比如用户1第一次的推理路径是 A-> B -> C -> D，第二次的查询类似，就可以复用一部分路径 节省时间

        await self._update_current_sub_query(state)
        try:
            state["should_continue"] = False
            if state["sub_queries"]:
                current_query = state["current_sub_query"]
                current_entities = state["current_entities"]
                current_functions = state["current_functions"]
                current_intent = state["current_intent"]
            else:
                await self.write_backtrack(error_msg="No Subquery Information Received", data=state)
                raise ValueError
            think_prompt = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT),
                ('user', USER_PROMPT)
            ])

            func_schemas = await self.intent_recognizer.get_function_schemas(current_functions)
            func_info = json.dumps(func_schemas, ensure_ascii=False, indent=2)
            exec_func_info = json.dumps(state["executed_functions"], ensure_ascii=False, indent=2)
            results_info = json.dumps(state["current_result"][-3:], ensure_ascii=False, indent=2)

            sub_query_context = ""
            total = len(state["sub_queries"])
            current_idx = state["current_sub_query_index"]
            sub_query_context = f"当前正在处理第 {current_idx + 1}/{total} 个子查询。" # 写出去 别在这里碍眼
            self.logger.info(sub_query_context)

            prev_results = [{"sub_query": sq["sub_query"], "results": sq["results"]} for sq in state["sub_queries"][:current_idx] if sq.get("results")]
            if prev_results:
                sub_query_context += f"\n\n前面子查询的结果：\n{json.dumps(prev_results, ensure_ascii=False, indent=2)}" # 写出去 别在这里碍眼

            error_context = ""
            # TODO 参数错误要特殊处理 优先级不高
            if "param_error" in state and state["param_error"]:
                last_error = state["last_error"]
                if last_error.get("error") == "missing_required_parameters": # 写出去 别在这里碍眼
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
            try:
                if is_think:
                    _, res_context = parse_think_content(response.content)
                    thought_result = json.loads(res_context)
                else:
                    thought_result = json.loads(response.content)
            except:
                state["error"] = ErrorType.RTMODEL
                error_data = {
                    "origin_query": state["original_query"],
                    "all_query": state["sub_queries"],
                    "current_query": state["current_sub_query"].get("sub_query"),
                    "model_result": response
                }
                await self.write_backtrack(error_type=ErrorType.RTMODEL, data=error_data)

            state["thoughts"].append({
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "sub_query_index": state["current_sub_query_index"],
                "sub_query": current_query,
                "content": thought_result
            })

            state["actions"].append({
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "sub_query_index": state["current_sub_query_index"],
                "action": thought_result.get("next_action", {})
            })
            
        except Exception as e:
            state["error"] = ErrorType.RT
            await self.write_backtrack(error_type=ErrorType.RT, error_msg=e, data=self._common_error_data(state))
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
                state["error"] = "No executable Action"
                return state
            
            current_action = state["actions"][-1]["action"]
            func_name = current_action.get("function_name")
            params = current_action.get("parameters", {})
            result = await self._call_function(func_name, params, state)
            if not result:
                bad_case_data = {
                    "func_name": func_name,
                    "params": params,
                    "state_snapshot": {
                        "query": state.get("original_query"),
                        "iteration": state.get("iteration_count")
                    }
                }
                await self.write_backtrack(error_type=ErrorType.COMMON, error_msg="Func Call执行返回结果为空", data=bad_case_data)

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
                state["current_result"].extend(result if isinstance(result, list) else [result])

            if is_end_signal:
                current_idx = state["current_sub_query_index"]
                self.logger.info(f"the model calls {func_name}, and the current subquery is complete.")
                if state["current_sub_query_index"] >= len(state["sub_queries"]):
                    state["func_end"] = True
                else:
                    state["sub_queries"][current_idx]["exe_process_data"] = {
                        "iteration_count": state["iteration_count"],
                        "all_result": state["current_result"], 
                        "thoughts": state["thoughts"],
                        "actions": state["actions"],
                        "observations": state["observations"],
                        "exec_func_info": state["executed_functions"]
                    }
                    state["sub_queries"][current_idx]["result"] = state["current_result"][-1]
                    state["current_sub_query_index"]+=1
                    state["should_continue"] = True   
                return state  

            # TODO 这里应该直接回ReThink模块 优先级不高 后面再改
            if is_param_error:
                state["param_error"] = result
                self.logger.warning(f"Missing parameter: {result.get('message')}")
            
        except Exception as e:
            state["error"] = ErrorType.EXE
            await self.write_backtrack(error_type=ErrorType.EXE, error_msg=e, data=self._common_error_data(state))
        return state
    
    @log_execution_time("Evaluate Result")
    async def _evaluate_result(self, state: AgentState) -> AgentState:
        if state["should_continue"]:
            return state
        current_idx = state["current_sub_query_index"]
        current_sq = state["sub_queries"][current_idx] if current_idx < len(state["sub_queries"]) else None
        try:
            state["iteration_count"] += 1
            state["total_iteration_count"] += 1
            if state["iteration_count"] >= state["max_iterations"]:
                self.logger.warning(
                f'SubQuery "{current_sq}" has reached the maximum number of iterations {state["max_iterations"]}, '
                f'so it is forcibly stopped. (Current iteration: {state["iteration_count"]})'
            )
                await self.write_backtrack(error_type=ErrorType.COMMON, error_msg=f"达到最大迭代次数 {state['max_iterations']}，将采用最后一个步长的答案作为记录，跳转到下一query",data=self._common_error_data(state))
                state["sub_queries"][current_idx]["result"] = state["current_result"][-1]
                # 这里记录其他为空是因为 后面汇总答案的时候 不准备使用这个子query的答案 因为不确定是否正确
                state["sub_queries"][current_idx]["exe_process_data"] = {
                    "iteration_count": state["iteration_count"],
                    "all_result": [], 
                    "thoughts": [],
                    "actions": [],
                    "observations": [],
                    "exec_func_info": []
                }
                state["current_sub_query_index"] += 1
                if state["current_sub_query_index"] >= len(state["sub_queries"]):
                    state["should_continue"] = False
                    state["evaluation_result"] = {
                        "should_continue": False,
                        "reason": "all subqueries have been completed."
                    }
                else:
                    state["should_continue"] = True
                    state["evaluation_result"] = {
                        "should_continue": True,
                        "reason": f"Continue processing the subquery: {state['current_sub_query_index'] + 1} "
                    }
                return state
            if not self.result_evaluator.quick_check(state["current_result"]):
                state["should_continue"] = True
                return state

            if current_sq:
                sq_eval_result = await self.result_evaluator.evaluate(
                    current_sq["sub_query"],
                    state["executed_functions"],
                    state["current_result"][-1]
                )
                # @Elian: if the current subquery is complete, switch to the next one.
                if not sq_eval_result.get("should_continue"):
                    # The result of the current subquery should be reflected in the subquery's result.
                    # current_sub_query/current_entities/current_functions/current_intent/current_result/思考/行动/观测/iteration_count/exec_func_info
                    # It needs to be cleared later.
                    state["sub_queries"][current_idx]["exe_process_data"] = {
                        "iteration_count": state["iteration_count"],
                        "all_result": state["current_result"], 
                        "thoughts": state["thoughts"],
                        "actions": state["actions"],
                        "observations": state["observations"],
                        "exec_func_info": state["executed_functions"]
                    }
                    state["sub_queries"][current_idx]["result"] = state["current_result"][-1]
                    self.logger.info(f"subquery {current_idx + 1} completed.")
                    state["current_sub_query_index"] += 1
                    

                    if state["current_sub_query_index"] >= len(state["sub_queries"]):
                        state["should_continue"] = False
                        state["evaluation_result"] = {
                            "should_continue": False,
                            "reason": "all subqueries have been completed."
                        }
                    else:
                        state["should_continue"] = True
                        state["evaluation_result"] = {
                            "should_continue": True,
                            "reason": f"Continue processing the subquery: {state['current_sub_query_index'] + 1}"
                        }
                else:
                    state["should_continue"] = True
                    state["evaluation_result"] = sq_eval_result
            else:
                state["should_continue"] = False
                state["evaluation_result"] = {
                    "should_continue": False,
                    "reason": "all subqueries have been completed."
                }
            
        except Exception as e:
            state["error"] = ErrorType.ER
            await self.write_backtrack(error_type=ErrorType.ER, error_msg=e, data=self._common_error_data(state))
        return state
    
    @log_execution_time("Generate Answer")
    async def _generate_answer(self, state: AgentState) -> AgentState:
        results_count = 0
        for sub_query in state["sub_queries"]:
            if sub_query.get("results"):
                results_count+=1
        try:
            if state.get("error"):
                state["final_answer"] = "系统繁忙, 请稍后重试"
                state["final_answer_metadata"] = {
                    "total_iterations": state["total_iteration_count"], # total_iteration_count
                    "functions_used": len(state["executed_functions"]), 
                    "results_count": results_count
                }
                return state
            
            answer_prompt = ChatPromptTemplate.from_messages([
                ("system", FIN_SYSTEM_PROMPT),
                ("user", FIN_USER_PROMPT)
            ])
            process_steps = []
            i = 0
            for sub_query in state["sub_queries"]:
                if not sub_query.get("exe_process_data")["thoughts"]:
                    continue
                process_steps.append(
                    f'第{i+1}个查询为：{sub_query.get("sub_query")}:\n'
                    f'它的答案为: {sub_query.get("results")}\n '
                    f'  思考: {sub_query.get("exe_process_data")["thoughts"][-1]}\n'
                    f'  行动: {sub_query.get("exe_process_data")["actions"][-1]}\n'
                    f'  观察: {sub_query.get("exe_process_data")["observations"][-1]}'
                )
                i+=1
            process_str = "".join(process_steps)
            
            chain = answer_prompt | self.llm
            response = await chain.ainvoke({
                "query": state["original_query"],
                "process": process_str
            })
            
            state["final_answer"] = response.content

            
            state["final_answer_metadata"] = {
                "total_iterations": state["total_iteration_count"], # total_iteration_count
                "functions_used": len(state["executed_functions"]), 
                "results_count": results_count
            }
            # TODO 存到短期 中期 还是长期? 中间过程怎么存? 
            self.memory_store.add_to_short_term(state["session_id"], {
                "query": state["original_query"],
                "answer": state["final_answer"],
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            state["error"] = ErrorType.GA
            await self.write_backtrack(error_type=ErrorType.GA, error_msg=e, data=self._common_error_data(state))
        return state
    
    async def _update_current_sub_query(self, state: AgentState) -> None:
        # TODO 更新到下一个子查询的时候 需要情况当前的current_sub_query/current_entities/current_functions/current_intent/current_result/思考/行动/观测/iteration_count/exec_func_info
        if not state["sub_queries"]:
            return
        current_idx = state["current_sub_query_index"]
        previous_idx = state.get("_previous_sub_query_index", -1)
        if current_idx != previous_idx:
            state["current_sub_query"] = []
            state["current_entities"] = []
            state["current_functions"] = []
            state["current_intent"] = []
            state["current_result"] = []
            state["thoughts"] = []
            state["actions"] = []
            state["observations"] = []
            state["iteration_count"] = 0
            state["executed_functions"] = []
            state["_previous_sub_query_index"] = current_idx
            state["evaluation_result"] = []
            
        if current_idx < len(state["sub_queries"]):
            state["current_sub_query"] = state["sub_queries"][current_idx]["sub_query"]
            state["current_entities"] = state["sub_queries"][current_idx]["entities"]
            state["current_functions"] = [
                f["function_name"] for f in state["sub_queries"][current_idx]["relevant_functions"]
            ]
            state["current_intent"] = state["sub_queries"][current_idx]["type"] + ": " + state["sub_queries"][current_idx]["description"]
            state["current_result"] = []

    def _should_continue(self, state: AgentState) -> str:
        if state.get("error"):
            return "finish"
        if not state.get("should_continue", False):
            return "finish"
        return "continue"
    
    def _check_func_continue(self, state: AgentState) -> str:
        if state.get("func_end"):
            return "finish"
        return "continue"
    
    def _check_error_or_continue(self, state: AgentState) -> str:
        if state.get("error"):
            return "error"
        return "continue"
    
    async def _call_function(self, func_name: str, params: Dict[str, Any], state: AgentState) -> Any:
        """调用func call"""
        end_signals = ["end_of_turn", "end_task", "finish", "complete", "none", "null", "None"]
        if func_name in end_signals or not func_name:
            self.logger.info(f"模型调用 {func_name or 'empty'}，任务已完成")
            return {"message": "任务完成"}
        
        if func_name not in self.tools:
            await self.write_backtrack(error_msg="未知函数名称", data={"error": f"未知函数: {func_name}"})
            raise ValueError
        
        tool = self.tools[func_name]
        required_params = await self._get_required_params(tool)
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
                await self.write_backtrack(error_msg="missing_required_parameters", data=f"函数 {func_name} 所需要的参数为: {required_params}, 缺少必须参数: {', '.join(missing_params)}")
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
            await self.write_backtrack(error_msg=error_msg, data={
                    "func_name": func_name,
                    "params": params,
                    "error_type": type(e).__name__
                })
            return {"error": error_msg}
    
    def _summarize_result(self, result: Any) -> str:
        if not result:
            return "无结果"
        if isinstance(result, list):
            return f"返回 {len(result)} 条记录"
        elif isinstance(result, dict):
            return f"返回字典，包含 {len(result)} 个字段"
        else:
            return str(result)[:100]
        
    async def _get_required_params(self, tool) -> List[str]:
        required = []
        try:
            if hasattr(tool, 'args') and hasattr(tool.args, '__annotations__'):
                import inspect
                sig = inspect.signature(tool.func)
                for param_name, param in sig.parameters.items():
                    if param.default == inspect.Parameter.empty and param_name != 'self':
                        required.append(param_name)
        except Exception:
            await self.write_backtrack(error_type=ErrorType.COMMON, data={"tool": tool, "required": required})
        return required
    
    def _validate_required_params(self, params: Dict[str, Any], required_params: List[str]) -> bool:
        for param in required_params:
            if param not in params or params[param] is None:
                return False
        return True
    
    def _common_error_data(self, state: AgentState) -> Dict[Any, Any]:
        return {
                "origin_query": state["original_query"],
                "all_query": state["sub_queries"],
                "current_query": state["current_query"],
                "current_query_position": f'{state["current_sub_query_index"]}/{len(state["sub_queries"])}',
                "current_result": state["current_result"],
                "meta_data": {
                    "thoughts": state["thoughts"],
                    "actions": state["actions"],
                    "observations": state["observations"]
                }
                }
    
    async def run(self, query: str, user_id: str, session_id: str) -> Dict[str, Any]:
        # external variables
        initial_state: AgentState = {
            "original_query": query,
            "user_id": user_id,
            "session_id": session_id,
            "max_iterations": self.settings.sub_query_max_iterations,
            "start_time": datetime.now().isoformat(),
        }
        try:
            final_state = await self.graph.ainvoke(
                initial_state,
                config={"recursion_limit": 30} # TODO 在配置文件里面写吧
            )
        except RecursionError as e:
            self.logger.error(f"Recursion constraint error: {str(e)}")
            return {
                **initial_state,
                "error": f"达到递归限制，系统强制停止: {str(e)}",
                "final_answer": "系统繁忙 请您稍后再试"
            }
        
        return final_state