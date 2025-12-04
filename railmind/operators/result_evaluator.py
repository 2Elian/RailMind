from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai.chat_models.base import BaseChatOpenAI

from railmind.config import get_settings


class ResultEvaluator:
    def __init__(self, llm_instance: BaseChatOpenAI = None):
        self.llm = llm_instance
        settings = get_settings()
        
        self.eval_prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个专业的结果评估助手。评估函数执行结果是否满足用户需求。

评估维度：
1. 完整性：结果是否包含所有必要信息
2. 相关性：结果与用户查询的相关程度
3. 准确性：结果是否准确可靠
4. 是否需要继续：判断是否需要执行更多函数来获取完整答案

输出格式（JSON）：
{{
    "completeness": {{
        "score": 0.8,
        "missing_info": ["缺失的信息1", "缺失的信息2"],
        "is_complete": true/false
    }},
    "relevance": {{
        "score": 0.9,
        "reason": "相关性说明"
    }},
    "accuracy": {{
        "score": 0.85,
        "confidence": 0.9,
        "potential_issues": ["潜在问题1"]
    }},
    "should_continue": true/false,
    "next_action_suggestion": "建议的下一步操作（如果需要继续）",
    "overall_assessment": "总体评估"
}}"""),
            ("user", """原始查询：{query}

已执行的函数：
{executed_functions}

当前结果：
{current_results}

请评估这些结果是否足以回答用户的查询。""")
        ])
    
    async def evaluate(
        self,
        query: str,
        executed_functions: List[Dict[str, Any]],
        current_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """评估当前结果
        
        Args:
            query: 原始查询
            executed_functions: 已执行的函数列表
            current_results: 当前结果列表
        
        Returns:
            评估结果
        """
        # 格式化函数执行信息
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
        
        # 解析 LLM 响应
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
        """快速检查结果是否为空或无效
        
        Args:
            results: 结果列表
        
        Returns:
            是否有效
        """
        if not results:
            return False
        
        # 检查是否所有结果都为空
        for r in results:
            if r and len(str(r)) > 10:  # 简单的非空检查
                return True
        
        return False
