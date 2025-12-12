from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class AgentState(TypedDict):
    original_query: str
    user_id: str
    session_id: str

    rewritten_query: str

    sub_queries: List[Dict[str, Any]] 

    current_sub_query_index: int
    current_sub_query: Dict[str, Any]
    current_functions: List[str] 
    current_entities: List[Dict[str, Any]]
    current_intent: str
    current_result: List[Any]
    thoughts: List[Dict[str, Any]]  
    actions: List[Dict[str, Any]] 
    observations: List[Dict[str, Any]] 

    executed_functions: List[Dict[str, Any]]

    evaluation_result: Dict[str, Any]
    should_continue: bool
    func_end: bool

    memory_context: Dict[str, Any]

    final_answer: str
    final_answer_metadata: Dict[str, Any]

    iteration_count: int
    total_iteration_count: int
    max_iterations: int
    start_time: str
    error: Optional[str]
    param_error: Optional[str]


class ErrorType(str, Enum):
    COMMON = "CommonFailed"
    RW = "QueryRewriteFailed"
    IR = "IntentRecognitionFailed"
    RTMODEL = "ReThinkModelFailed"
    RT = "ReThinkFailed"
    EXE = "ExecuteActionFailed"
    ER = "EvalResultFailed"
    GA = "GenerateAnswerFailed"