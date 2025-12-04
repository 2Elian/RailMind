from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai.chat_models.base import BaseChatOpenAI

from railmind.operators.templates.intention import PROMPT
from railmind.utils import *

class QueryRewriter:
    def __init__(self, llm_instance: BaseChatOpenAI = None):
        self.llm = llm_instance
        self.rewrite_prompt = ChatPromptTemplate.from_messages([
            ("system", PROMPT['system_requery']),
            ("user", "请改写以下查询：\n{query}")
        ])
    
    async def rewrite(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        chain = self.rewrite_prompt | self.llm # A | B | C 先执行 A，然后把 A 的输出传给 B，再传给 C
        
        query_with_context = query
        if context:
            query_with_context = f"历史记忆上下文：{context}\n\n当前查询：{query}"
        response = await chain.ainvoke({"query": query_with_context})
        is_think = is_think_model(self.llm.model_name)
        try:
            if is_think:
                _, res_context = parse_think_content(response.content)
                result = json.loads(res_context)
            else:
                result = json.loads(response.content)
        except:
            result = {
                "rewritten_query": response.content.strip()
            }
        
        return result
    
    async def batch_rewrite(self, queries: List[str], contexts: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """批量改写查询"""
        tasks = []
        for i, query in enumerate(queries):
            ctx = contexts[i] if contexts else None
            tasks.append(self.rewrite(query, context=ctx))
        import asyncio
        return await asyncio.gather(*tasks)