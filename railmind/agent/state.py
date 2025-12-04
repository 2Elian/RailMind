from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime


class AgentState(TypedDict):
    """Agent状态的定义"""
    
    # 输入
    original_query: str
    user_id: str
    session_id: str
    
    # Query改写
    rewritten_query: str
    query_rewrite_result: Dict[str, Any]
    
    # 意图识别
    intent_result: Dict[str, Any]
    current_intent: Optional[int]  # 当前正在处理哪个子查询
    current_function: Optional[str]  # 正在调用哪个函数
    intermediate_results: Optional[Dict[str, Any]]  # 函数执行中间结果
    
    # ReAct循环
    thoughts: List[Dict[str, Any]]  # Thought 记录
    actions: List[Dict[str, Any]]  # Action 记录
    observations: List[Dict[str, Any]]  # Observation 记录
    
    # 执行结果
    executed_functions: List[Dict[str, Any]]
    accumulated_results: List[Dict[str, Any]]
    
    # 评估
    evaluation_result: Dict[str, Any]
    should_continue: bool
    
    # 记忆
    memory_context: Dict[str, Any]
    
    # 最终答案
    final_answer: str
    final_answer_metadata: Dict[str, Any]
    
    # 元信息
    iteration_count: int
    max_iterations: int
    start_time: str
    error: Optional[str]
