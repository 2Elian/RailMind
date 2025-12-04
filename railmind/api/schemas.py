from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class QueryRequest(BaseModel):
    """查询请求"""
    query: str = Field(..., description="用户查询")
    user_id: str = Field(default="default_user", description="用户ID")
    session_id: Optional[str] = Field(default=None, description="会话ID")


class QueryResponse(BaseModel):
    """查询响应"""
    success: bool
    answer: str
    metadata: Dict[str, Any]
    
    # ReAct 流程详情
    thoughts: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    
    # 原始状态（可选，用于调试）
    full_state: Optional[Dict[str, Any]] = None


class SessionRequest(BaseModel):
    """会话请求"""
    user_id: str
    metadata: Optional[Dict[str, Any]] = None


class SessionResponse(BaseModel):
    """会话响应"""
    session_id: str
    user_id: str
    created_at: str
