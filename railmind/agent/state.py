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

class StateBuilder:

    @staticmethod
    def init_state(state: AgentState, agent_instance) -> AgentState:
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
        state["memory_context"] = agent_instance.memory_store.get_session_context(
            state["session_id"]
        )
        return state

    @staticmethod
    def update_current_sub_query(state: AgentState) -> AgentState:
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
        return state