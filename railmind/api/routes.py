from fastapi import APIRouter, HTTPException
from datetime import datetime
import uuid
import traceback

from railmind.api.schemas import QueryRequest, QueryResponse, SessionRequest, SessionResponse
from railmind.agent.react_agent import ReActAgent
from railmind.operators.memory import get_memory_store
from railmind.function_call.kg_tools import TOOLS
from railmind.operators.logger import get_logger

router = APIRouter(prefix="/api", tags=["api"])
agent: ReActAgent = None
logger = get_logger(name="RailMind-Router")

def set_agent(agent_instance: ReActAgent):
    global agent
    agent = agent_instance


@router.post("/session", response_model=SessionResponse)
async def create_session(request: SessionRequest):
    """创建新会话"""
    try:
        session_id = f"session_{uuid.uuid4().hex[:16]}"
        memory_store = get_memory_store()
        
        memory_store.create_session(
            session_id=session_id,
            user_id=request.user_id,
            metadata=request.metadata
        )
        
        return SessionResponse(
            session_id=session_id,
            user_id=request.user_id,
            created_at=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error("/session interface Exception:")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"创建会话失败: {str(e)}")


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """处理用户查询core"""
    try:
        session_id = request.session_id or f"session_{uuid.uuid4().hex[:16]}"
        memory_store = get_memory_store()
        if session_id not in memory_store.session_metadata:
            memory_store.create_session(session_id, request.user_id)
        logger.info(f"get user_id: {request.user_id} query is : {request.query}")
        result = await agent.run(
            query=request.query,
            user_id=request.user_id,
            session_id=session_id
        )
        response = QueryResponse(
            success=result.get("error") is None,
            answer=result.get("final_answer", "error"),
            metadata={
                "session_id": session_id,
                "user_id": request.user_id,
                "iterations": result.get("iteration_count", 0),
                "functions_used": len(result.get("executed_functions", [])),
                "timestamp": datetime.now().isoformat(),
                "error": result.get("error")
            },
            thoughts=result.get("thoughts", []),
            actions=result.get("actions", []),
            observations=result.get("observations", []),
            full_state=result  # 包含完整状态用于调试
        )
        
        return response
        
    except Exception as e:
        logger.error("/query interface Exception:")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"处理查询失败: {str(e)}")


@router.get("/session/{session_id}/history")
async def get_session_history(session_id: str):
    """获取会话历史"""
    try:
        memory_store = get_memory_store()
        context = memory_store.get_session_context(session_id)
        
        return {
            "session_id": session_id,
            "short_term_memory": context.get("short_term", []),
            "long_term_memory": context.get("long_term", []),
            "metadata": context.get("metadata", {})
        }
    except Exception as e:
        logger.error(f"/session/{session_id}/history interface Exception:")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"获取历史失败: {str(e)}")


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    try:
        memory_store = get_memory_store()
        memory_store.clear_session(session_id)
        
        return {
            "message": f"会话 {session_id} 已删除",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"/session/{session_id} interface Exception:")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")


@router.get("/functions")
async def get_available_functions():
    """获取可用函数列表"""
    return {
        "functions": [
            {
                "name": tool.name,
                "description": tool.description,
                "args_schema": tool.args_schema.schema() if tool.args_schema else {}
            }
            for tool in TOOLS
        ]
    }
