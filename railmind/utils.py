import re
import json
import time
import functools
import asyncio
from typing import Callable, Tuple, Dict, Any

from railmind.operators.logger import get_logger
from railmind.api.enum.think_model import THINK_MODELS

def is_think_model(model_name: str) -> bool:
    return any(model_name.lower() == m.value for m in THINK_MODELS)

def parse_think_content(content: str) -> Tuple[str, Dict[str, Any]]:
    think_match = re.search(r"<think>\s*(.*?)\s*</think>", content, re.DOTALL)
    think_text = think_match.group(1).strip() if think_match else ""
    context_part = content.split("</think>")[-1].strip()
    return think_text, context_part

def log_execution_time(func_name: str = None):
    """
    装饰器：记录函数执行完成时间
    使用方式：
        @log_execution_time()  # 自动获取函数名
        async def your_function(self, state):
            pass
        
        @log_execution_time("custom_name")  # 自定义显示名称
        async def another_function(self, state):
            pass
    """
    logger = get_logger("Execution_Time")
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                end_time = time.perf_counter()
                execution_time = end_time - start_time
                
                display_name = func_name if func_name else func.__name__
                logger.info(f"{display_name} 执行完成，耗时: {execution_time:.4f}秒")
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.perf_counter() 
                execution_time = end_time - start_time
                
                display_name = func_name if func_name else func.__name__
                logger.info(f"{display_name} 执行完成，耗时: {execution_time:.4f}秒")
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator