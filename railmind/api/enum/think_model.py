from enum import Enum

class ThinkModelType(Enum):
    QWEN30B = "qwen30b"
    THINK_V2 = "think-v2"
    THINK_PRO = "think-pro"
    GPT = "gpt-4"
    LAMBDA = "lambda-1"

THINK_MODELS = {ThinkModelType.QWEN30B, ThinkModelType.THINK_V2, ThinkModelType.THINK_PRO}
