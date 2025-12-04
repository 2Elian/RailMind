import logging
import json
import os
import inspect
from typing import Any, Optional

class BaseAgent:
    def __init__(self, error_backtracking_log_path: str):
        os.makedirs(error_backtracking_log_path, exist_ok=True)
        log_path = os.path.join(error_backtracking_log_path, "error_backtracking.log")

    def write_backtrack(
        self,
        error_msg: str,
        data: Any,
        ):
        log_entry = {
            "class_name": self.__class__.__name__,
            "func_name": inspect.stack()[1].function,
            "error_msg": error_msg,
            "data": data
        }

        log_str = json.dumps(log_entry, ensure_ascii=False)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(log_str + "\n")