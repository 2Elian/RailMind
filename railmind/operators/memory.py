from typing import Dict, Any, List, Optional
import json
import time
from datetime import datetime, timedelta

from railmind.config import get_settings


class MemoryStore:
    """记忆存储模块 - 用户级长期记忆 + 会话短期记忆"""
    
    def __init__(self):
        # 使用内存存储 --> 生产环境应使用 Redis + Embedding + BM25 记忆召回
        self.long_term_memory: Dict[str, List[Dict[str, Any]]] = {}  # user_id -> memories
        self.short_term_memory: Dict[str, List[Dict[str, Any]]] = {}  # session_id -> memories
        self.session_metadata: Dict[str, Dict[str, Any]] = {}  # session_id -> metadata
        self.setting = get_settings()
    
    def add_to_long_term(self, user_id: str, memory: Dict[str, Any]):
        """添加到长期记忆
        Args:
            user_id: 用户ID
            memory: 记忆内容
        """
        if user_id not in self.long_term_memory:
            self.long_term_memory[user_id] = []
        
        memory_entry = {
            "content": memory,
            "timestamp": datetime.now().isoformat(),
            "access_count": 0,
            "importance": memory.get("importance", 0.5)
        }
        
        self.long_term_memory[user_id].append(memory_entry)
    
        # 保持最多k条长期记忆
        if len(self.long_term_memory[user_id]) > self.setting.long_memory_num:
            # 如果超出k条 --> 按重要性和访问次数排序 删除最不重要的
            sorted_memories = sorted(
                self.long_term_memory[user_id],
                key=lambda x: x["importance"] * (1 + x["access_count"]),
                reverse=True
            )
            self.long_term_memory[user_id] = sorted_memories[:100]
    
    def add_to_short_term(self, session_id: str, memory: Dict[str, Any]):
        """添加到短期记忆-->会话级别
        Args:
            session_id: 会话ID
            memory: 记忆内容
        """
        if session_id not in self.short_term_memory:
            self.short_term_memory[session_id] = []
        
        memory_entry = {
            "content": memory,
            "timestamp": datetime.now().isoformat()
        }
        
        self.short_term_memory[session_id].append(memory_entry)
        # 保持最多k条短期记忆
        if len(self.short_term_memory[session_id]) > self.setting.shot_memory_num:
            # 如果超出k条 --> 保留最新的k条
            self.short_term_memory[session_id] = self.short_term_memory[session_id][-20:]
    
    def get_long_term_memory(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取长期记忆
        Args:
            user_id: 用户ID
            limit: 返回条数
        """
        if user_id not in self.long_term_memory:
            return []
        
        # 按时间倒序返回
        memories = sorted(
            self.long_term_memory[user_id],
            key=lambda x: x["timestamp"],
            reverse=True
        )[:limit]
        
        # 增加访问计数
        for mem in memories:
            mem["access_count"] += 1
        
        return [m["content"] for m in memories]
    
    def get_short_term_memory(self, session_id: str) -> List[Dict[str, Any]]:
        """获取短期记忆
        Args:
            session_id: 会话ID
        """
        if session_id not in self.short_term_memory:
            return []
        
        return [m["content"] for m in self.short_term_memory[session_id]]
    
    def search_long_term_memory(self, user_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        # TODO 
        搜索长期记忆 TODO embedding + bm25召回
        
        Args:
            user_id: 用户ID
            query: 搜索查询
            limit: 返回条数
        """
        if user_id not in self.long_term_memory:
            return []
        
        # 简单的关键词匹配
        matched = []
        for mem_entry in self.long_term_memory[user_id]:
            content_str = json.dumps(mem_entry["content"], ensure_ascii=False)
            if query.lower() in content_str.lower():
                matched.append(mem_entry)
        
        # 按相关性排序（这里简化为按时间）
        matched = sorted(matched, key=lambda x: x["timestamp"], reverse=True)[:limit]
        
        return [m["content"] for m in matched]
    
    def create_session(self, session_id: str, user_id: str, metadata: Dict[str, Any] = None):
        """创建新会话
        Args:
            session_id: 会话ID
            user_id: 用户ID
            metadata: 会话元数据
        """
        self.session_metadata[session_id] = {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
    
    def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取会话上下文--> 短期记忆 + 部分长期记忆
        Args:
            session_id: 会话ID
        """
        # 新会话的记忆为空
        if session_id not in self.session_metadata:
            return {"short_term": [], "long_term": [], "metadata": {}}
        
        user_id = self.session_metadata[session_id]["user_id"]
        return {
            "short_term": self.get_short_term_memory(session_id),
            "long_term": self.get_long_term_memory(user_id, limit=5),
            "metadata": self.session_metadata[session_id]["metadata"]
        }
    
    def clear_session(self, session_id: str):
        """清除会话记忆"""
        if session_id in self.short_term_memory:
            del self.short_term_memory[session_id]
        if session_id in self.session_metadata:
            del self.session_metadata[session_id]


# 全局记忆存储实例
_memory_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
