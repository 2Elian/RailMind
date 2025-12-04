from typing import Dict, Any, Callable
from datetime import datetime
import json
import functools
import asyncio
import time
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
from railmind.utils import log_execution_time

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
        
        return workflow.compile()
    
    async def _init_state(self, state: AgentState) -> AgentState:
        self.logger.info("[Start] init state")
        state["thoughts"] = []
        state["actions"] = []
        state["observations"] = []
        state["executed_functions"] = []
        state["accumulated_results"] = []
        state["iteration_count"] = 0
        state["max_iterations"] = 5
        state["start_time"] = datetime.now().isoformat()
        state["should_continue"] = True
        state["error"] = None
        
        # load memory context
        state["memory_context"] = self.memory_store.get_session_context(
            state["session_id"]
        )
        self.logger.info(state)
        self.logger.info("[End] init state")
        return state
    
    @log_execution_time("rewrite_query")
    async def _rewrite_query(self, state: AgentState) -> AgentState:
        self.logger.info("[Start] rewrite query")
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
        self.logger.info(state)
        self.logger.info("[End] rewrite query")
        return state
    
    @log_execution_time("intent_recognize")
    async def _recognize_intent(self, state: AgentState) -> AgentState:
        self.logger.info("[Start] recognize_intent")
        try:
            result = await self.intent_recognizer.recognize(state["rewritten_query"])
            # TODO 如何做后续的处理？
            state["intent_result"] = result
            state["entities"] = result.get("entities", [])
            state["relevant_functions"] = [
                f["function_name"]
                for f in result.get("relevant_functions", [])
            ]
            
        except Exception as e:
            state["error"] = f"意图识别失败: {str(e)}"
            state["relevant_functions"] = ["search_entity"]
            self.write_backtrack(error_msg=e, data=state)
        self.logger.info(state)
        self.logger.info("[End] recognize_intent")
        return state
    
    async def _react_think(self, state: AgentState) -> AgentState:
        self.logger.info("[Start] react_think")
        try:
            think_prompt = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT),
                ('user', USER_PROMPT)
            ])
            
            # 格式化function call
            func_schemas = self.intent_recognizer.get_function_schemas(state["relevant_functions"])
            func_info = json.dumps(func_schemas, ensure_ascii=False, indent=2)
            
            # 格式化已执行函数
            exec_func_info = json.dumps(state["executed_functions"], ensure_ascii=False, indent=2)
            
            # 格式化当前结果
            results_info = json.dumps(state["accumulated_results"][-3:], ensure_ascii=False, indent=2)
            
            chain = think_prompt | self.llm
            # TODO 多个子意图 --> 哪些能并行？ 哪些是需要先执行A再带着A结果执行B的？
            response = await chain.ainvoke({
                "available_functions": func_info,
                "query": state["rewritten_query"],
                "intent": json.dumps(state["intent_result"], ensure_ascii=False),
                "entities": json.dumps(state["entities"], ensure_ascii=False),
                "executed_functions": exec_func_info,
                "current_results": results_info
            })
            
            # TODO 解析思考结果 要判断是否为思考模型
            try:
                thought_result = json.loads(response.content)
            except:
                thought_result = {
                    "thought": response.content,
                    "reasoning": "无法解析 JSON",
                    "next_action": {
                        "function_name": state["relevant_functions"][0] if state["relevant_functions"] else "search_entity",
                        "parameters": {},
                        "reason": "默认行动"
                    },
                    "expected_outcome": ""
                }
            
            # 记录 Thought
            state["thoughts"].append({
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "content": thought_result
            })
            
            # 记录 Action
            state["actions"].append({
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "action": thought_result.get("next_action", {})
            })
            
        except Exception as e:
            state["error"] = f"ReAct 思考失败: {str(e)}"
            # 添加默认 action
            state["actions"].append({
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "action": {
                    "function_name": "search_entity",
                    "parameters": {},
                    "reason": "异常恢复"
                }
            })
            self.write_backtrack(error_msg=e, data=state)
        self.logger.info("[End] react_think")
        return state
    
    def _execute_action(self, state: AgentState) -> AgentState:
        self.logger.info("[Start] execute_action")
        try:
            if not state["actions"]:
                state["error"] = "没有可执行的 Action"
                return state
            
            current_action = state["actions"][-1]["action"]
            func_name = current_action.get("function_name")
            params = current_action.get("parameters", {})
            
            # 执行函数
            result = self._call_function(func_name, params, state)
            
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
            
            # 记录执行的函数
            state["executed_functions"].append({
                "name": func_name,
                "parameters": params,
                "result_summary": observation["result_summary"]
            })
            
            # 累积结果
            if result:
                state["accumulated_results"].extend(result if isinstance(result, list) else [result])
            
        except Exception as e:
            state["error"] = f"执行 Action 失败: {str(e)}"
            state["observations"].append({
                "iteration": state["iteration_count"],
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            self.write_backtrack(error_msg=e, data=state)
        self.logger.info("[End] execute_action")
        return state
    
    def _evaluate_result(self, state: AgentState) -> AgentState:
        self.logger.info("[Start] evaluate_result")
        try:
            state["iteration_count"] += 1
            if state["iteration_count"] >= state["max_iterations"]:
                state["should_continue"] = False
                state["evaluation_result"] = {
                    "should_continue": False,
                    "reason": "达到最大迭代次数"
                }
                return state
            
            if not self.result_evaluator.quick_check(state["accumulated_results"]):
                state["should_continue"] = True
                return state
            
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
        self.logger.info("[End] evaluate_result")
        return state
    
    def _generate_answer(self, state: AgentState) -> AgentState:
        self.logger.info("[Start] generate_answer")
        try:
            answer_prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个专业的答案生成助手。根据查询和收集的信息，生成清晰、完整的自然语言答案。

要求：
1. 整合所有相关结果
2. 使用自然流畅的语言
3. 如果信息不完整，明确说明
4. 添加必要的解释说明

输出格式：直接输出自然语言答案即可。"""),
                ("user", """用户查询：{query}

收集到的信息：
{results}

执行过程：
{process}

请生成最终答案。""")
            ])
            
            # 格式化结果
            results_str = json.dumps(state["accumulated_results"], ensure_ascii=False, indent=2)
            
            # 格式化执行过程
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
            response = chain.invoke({
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
            
            # 保存到记忆
            self.memory_store.add_to_short_term(state["session_id"], {
                "query": state["original_query"],
                "answer": state["final_answer"],
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            state["error"] = f"生成答案失败: {str(e)}"
            state["final_answer"] = "抱歉，无法生成答案。"
            self.write_backtrack(error_msg=e, data=state)
        self.logger.info("[End] generate_answer")
        return state
    
    # ========== 辅助函数 ==========
    
    def _should_continue(self, state: AgentState) -> str:
        """判断是否继续 ReAct 循环"""
        if state.get("error"):
            return "finish"
        if not state.get("should_continue", False):
            return "finish"
        return "continue"
    
    def _call_function(self, func_name: str, params: Dict[str, Any], state: AgentState) -> Any:
        """调用知识图谱函数"""
        if not params and state["entities"]:
            for entity in state["entities"]:
                if entity["type"] == "Station" and func_name in ["search_entity", "get_entity_relations", "get_neighbors"]:
                    params["entity_name"] = entity["value"]
                    break
        if func_name in self.tools:
            tool = self.tools[func_name]
            try:
                result_str = tool.invoke(params)
                return json.loads(result_str)
            except Exception as e:
                return {"error": f"函数执行失败: {str(e)}"}
        else:
            return {"error": f"未知函数: {func_name}"}
    
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
            "max_iterations": 5,
            "start_time": "",
            "error": None
        }
        final_state = await self.graph.ainvoke(initial_state)
        
        return final_state
    