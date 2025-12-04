import json
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai.chat_models.base import BaseChatOpenAI

from railmind.utils import is_think_model, parse_think_content
from railmind.config import get_settings
from railmind.function_call.kg_tools import TOOLS
from railmind.operators.templates.intention import PROMPT

class IntentRecognizer:
    def __init__(self, llm_instance: BaseChatOpenAI = None):
        self.llm = llm_instance
        self.available_tools = TOOLS
        self.func_list_str = "\n".join([
            f"- {tool.name}: {tool.description}"
            for tool in TOOLS
        ])
        
        self.intent_prompt = ChatPromptTemplate.from_messages([
            ("system", PROMPT['system_intent']),
            ("user", "请分析以下查询：{query}")
        ])
    
    async def recognize(self, query: str) -> Dict[str, Any]:
        chain = self.intent_prompt | self.llm
        response = await chain.ainvoke({"query": query, "func_list_str": self.func_list_str,})
        is_think = is_think_model(self.llm.model_name)
        try:
            if is_think:
                _, res_context = parse_think_content(response.content)
                result = json.loads(res_context)
            else:
                result = json.loads(response.content)
        except:
            result = {
                "intents": [],
                "queries": []
            }
        
        return result
    
    def get_function_schemas(self, function_names: List[str]) -> List[Dict[str, Any]]:
        """获取函数的详细schema
        Args:
            function_names: 函数名列表
        Returns:
            函数 schema 列表
        """
        schemas = []
        for tool in self.available_tools:
            if tool.name in function_names:
                schemas.append({
                    "name": tool.name,
                    "description": tool.description,
                    "args_schema": tool.args_schema.schema() if tool.args_schema else {}
                })
        return schemas
