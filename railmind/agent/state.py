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
    sub_queries: List[Dict[str, Any]] 
    
    # ReAct循环
    current_sub_query_index: int
    current_sub_query: Dict[str, Any]
    current_functions: List[str] 
    current_entities: List[Dict[str, Any]]
    current_intent: str
    thoughts: List[Dict[str, Any]]  # Thought 记录
    actions: List[Dict[str, Any]]  # Action 记录
    observations: List[Dict[str, Any]]  # Observation 记录
    
    # 执行结果
    executed_functions: List[Dict[str, Any]]
    accumulated_results: List[Dict[str, Any]]
    results_by_subquery: Dict[int, List[Any]] # 子查询的 独立结果
    
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
