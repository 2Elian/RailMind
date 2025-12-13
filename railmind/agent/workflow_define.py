from langgraph.graph import StateGraph, END

from railmind.agent.state import AgentState

class RailMindWorkFlowBuilder:
    @classmethod
    def create_workflow(cls, agent_instance) -> StateGraph:
        workflow = StateGraph(AgentState)
        
        # add node
        workflow.add_node("init", agent_instance._init_state)
        workflow.add_node("rewrite_query", agent_instance._rewrite_query)
        workflow.add_node("recognize_intent", agent_instance._recognize_intent)
        workflow.add_node("react_think", agent_instance._react_think)
        workflow.add_node("execute_action", agent_instance._execute_action)
        workflow.add_node("evaluate_result", agent_instance._evaluate_result)
        workflow.add_node("generate_answer", agent_instance._generate_answer)
        
        # set a start
        workflow.set_entry_point("init")
        
        # add edge
        workflow.add_edge("init", "rewrite_query")
        workflow.add_edge("rewrite_query", "recognize_intent")
        workflow.add_edge("recognize_intent", "react_think")
        workflow.add_edge("react_think", "execute_action")
        # workflow.add_edge("execute_action", "evaluate_result")
        
        # Conditional edge, determining whether to continue the loop.
        workflow.add_conditional_edges(
            "evaluate_result",
            agent_instance._should_continue,
            {
                "continue": "react_think",
                "finish": "generate_answer",
            }
        )
        # error conditional edge
        workflow.add_conditional_edges(
            "rewrite_query",
            agent_instance._check_error_or_continue,
            {
                "error": "generate_answer",
                "continue": "recognize_intent"
            }
        )
        workflow.add_conditional_edges(
            "recognize_intent",
            agent_instance._check_error_or_continue,
            {
                "error": "generate_answer",
                "continue": "react_think"
            }
        )
        workflow.add_conditional_edges(
            "react_think",
            agent_instance._check_error_or_continue,
            {
                "error": "generate_answer",
                "continue": "execute_action"
            }
        )
        workflow.add_conditional_edges(
            "execute_action",
            agent_instance._check_error_or_continue_for_exe,
            {
                "continue": "evaluate_result",
                "finish": "generate_answer",
                "error_to_answer": "generate_answer"
            }
        )
        workflow.add_edge("generate_answer", END)
        
        return workflow.compile(debug=False)