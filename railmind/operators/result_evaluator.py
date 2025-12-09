from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai.chat_models.base import BaseChatOpenAI

from railmind.operators.templates.eval_result import SYSTEM_PROMPT, USER_PROMPT


class ResultEvaluator:
    def __init__(self, llm_instance: BaseChatOpenAI = None):
        self.llm = llm_instance
        self.eval_prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("user", USER_PROMPT)
        ])
    
    async def evaluate(
        self,
        query: str,
        executed_functions: List[Dict[str, Any]],
        current_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        func_info = "\n".join([
            f"- {f.get('name', 'unknown')}: {f.get('result_summary', 'no summary')}"
            for f in executed_functions
        ])
        
        # 格式化结果
        results_info = "\n".join([
            f"- {i+1}. {str(r)[:200]}..."
            for i, r in enumerate(current_results)
        ])
        
        chain = self.eval_prompt | self.llm
        response = await chain.ainvoke({
            "query": query,
            "executed_functions": func_info,
            "current_results": results_info
        })
        try:
            import json
            result = json.loads(response.content)
        except:
            # 默认评估结果
            result = {
                "completeness": {
                    "score": 0.5,
                    "missing_info": [],
                    "is_complete": len(current_results) > 0
                },
                "relevance": {
                    "score": 0.5,
                    "reason": "无法解析评估结果"
                },
                "accuracy": {
                    "score": 0.5,
                    "confidence": 0.5,
                    "potential_issues": []
                },
                "should_continue": len(current_results) == 0,
                "next_action_suggestion": "",
                "overall_assessment": "评估失败，使用默认值"
            }
        
        return result
    
    def quick_check(self, results: List[Dict[str, Any]]) -> bool:
        if not results:
            return False

        for r in results:
            if r and len(str(r)) > 10:
                return True
        
        return False
