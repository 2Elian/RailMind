import abc
import re
import math
from typing import Any, List, Optional, Union, Dict
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import asyncio
import time
from datetime import datetime, timedelta
import logging

import openai
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, AsyncAzureOpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from transformers import AutoTokenizer

logger = logging.getLogger("12306-Agent-LLM-cli")


class TPM:
    def __init__(self, tpm: int = 20000):
        self.tpm = tpm
        self.record = {"tpm_slot": self.get_minute_slot(), "counter": 0}

    @staticmethod
    def get_minute_slot():
        current_time = time.time()
        dt_object = datetime.fromtimestamp(current_time)
        total_minutes_since_midnight = dt_object.hour * 60 + dt_object.minute
        return total_minutes_since_midnight

    async def wait(self, token_count, silent=False):
        current = time.time()
        dt_object = datetime.fromtimestamp(current)
        minute_slot = self.get_minute_slot()

        # get next slot, skip
        if self.record["tpm_slot"] != minute_slot:
            self.record = {"tpm_slot": minute_slot, "counter": token_count}
            return

        # check RPM exceed
        old_counter = self.record["counter"]
        self.record["counter"] += token_count
        if self.record["counter"] > self.tpm:
            logger.info("Current TPM: %s, limit: %s", old_counter, self.tpm)
            # wait until next minute
            next_minute = dt_object.replace(second=0, microsecond=0) + timedelta(
                minutes=1
            )
            _next = next_minute.timestamp()
            sleep_time = abs(_next - current)
            logger.warning("TPM limit exceeded, wait %s seconds", sleep_time)
            await asyncio.sleep(sleep_time)

            self.record = {"tpm_slot": self.get_minute_slot(), "counter": token_count}

        if not silent:
            logger.debug(self.record)


class RPM:
    def __init__(self, rpm: int = 1000):
        self.rpm = rpm
        self.record = {"rpm_slot": self.get_minute_slot(), "counter": 0}

    @staticmethod
    def get_minute_slot():
        current_time = time.time()
        dt_object = datetime.fromtimestamp(current_time)
        total_minutes_since_midnight = dt_object.hour * 60 + dt_object.minute
        return total_minutes_since_midnight

    async def wait(self, silent=False):
        current = time.time()
        dt_object = datetime.fromtimestamp(current)
        minute_slot = self.get_minute_slot()

        if self.record["rpm_slot"] == minute_slot:
            # check RPM exceed
            if self.record["counter"] >= self.rpm:
                # wait until next minute
                next_minute = dt_object.replace(second=0, microsecond=0) + timedelta(
                    minutes=1
                )
                _next = next_minute.timestamp()
                sleep_time = abs(_next - current)
                if not silent:
                    logger.info("RPM sleep %s", sleep_time)
                await asyncio.sleep(sleep_time)

                self.record = {"rpm_slot": self.get_minute_slot(), "counter": 0}
        else:
            self.record = {"rpm_slot": self.get_minute_slot(), "counter": 0}
        self.record["counter"] += 1

        if not silent:
            logger.debug(self.record)


@dataclass
class Token:
    text: str
    prob: float
    top_candidates: List = field(default_factory=list)
    ppl: Union[float, None] = field(default=None)

    @property
    def logprob(self) -> float:
        return math.log(self.prob)

class BaseTokenizer(ABC):
    def __init__(self, model_name: str = "cl100k_base"):
        self.model_name = model_name

    @abstractmethod
    def encode(self, text: str) -> List[int]:
        """Encode text -> token ids."""
        raise NotImplementedError

    @abstractmethod
    def decode(self, token_ids: List[int]) -> str:
        """Decode token ids -> text."""
        raise NotImplementedError

    def count_tokens(self, text: str) -> int:
        return len(self.encode(text))

    def chunk_by_token_size(
        self,
        content: str,
        *,
        overlap_token_size: int = 128,
        max_token_size: int = 1024,
    ) -> List[dict]:
        tokens = self.encode(content)
        results = []
        step = max_token_size - overlap_token_size
        for index, start in enumerate(range(0, len(tokens), step)):
            chunk_ids = tokens[start : start + max_token_size]
            results.append(
                {
                    "tokens": len(chunk_ids),
                    "content": self.decode(chunk_ids).strip(),
                    "chunk_order_index": index,
                }
            )
        return results

class TiktokenTokenizer(BaseTokenizer):
    def __init__(self, model_name: str = "cl100k_base"):
        import tiktoken
        super().__init__(model_name)
        self.enc = tiktoken.get_encoding(self.model_name)

    def encode(self, text: str) -> List[int]:
        return self.enc.encode(text)

    def decode(self, token_ids: List[int]) -> str:
        return self.enc.decode(token_ids)

class HFTokenizer(BaseTokenizer):
    def __init__(self, model_name: str = "cl100k_base"):
        super().__init__(model_name)
        self.enc = AutoTokenizer.from_pretrained(self.model_name)

    def encode(self, text: str) -> List[int]:
        return self.enc.encode(text, add_special_tokens=False)

    def decode(self, token_ids: List[int]) -> str:
        return self.enc.decode(token_ids, skip_special_tokens=True)


def get_tokenizer_impl(tokenizer_name: str = "cl100k_base") -> BaseTokenizer:
    return HFTokenizer(model_name=tokenizer_name)


class Tokenizer(BaseTokenizer):
    """
    Encapsulates different tokenization implementations based on the specified model name.
    """

    def __init__(self, model_name: str = "cl100k_base"):
        super().__init__(model_name)
        if not self.model_name:
            raise ValueError("TOKENIZER_MODEL must be specified in the ENV variables.")
        self._impl = get_tokenizer_impl(self.model_name)

    def encode(self, text: str) -> List[int]:
        return self._impl.encode(text)

    def decode(self, token_ids: List[int]) -> str:
        return self._impl.decode(token_ids)

    def count_tokens(self, text: str) -> int:
        return self._impl.count_tokens(text)


class BaseLLMWrapper(abc.ABC):
    """
    LLM client base class, agnostic to specific backends (OpenAI / Ollama / ...).
    """

    def __init__(
        self,
        *,
        system_prompt: str = "",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        repetition_penalty: float = 1.05,
        top_p: float = 0.95,
        top_k: int = 50,
        tokenizer: Optional[BaseTokenizer] = None,
        **kwargs: Any,
    ):
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.repetition_penalty = repetition_penalty
        self.top_p = top_p
        self.top_k = top_k
        self.tokenizer = tokenizer

        for k, v in kwargs.items():
            setattr(self, k, v)

    @abc.abstractmethod
    async def generate_answer(
        self, text: str, history: Optional[List[str]] = None, **extra: Any
    ) -> str:
        """Generate answer from the model."""
        raise NotImplementedError

    @abc.abstractmethod
    async def generate_topk_per_token(
        self, text: str, history: Optional[List[str]] = None, **extra: Any
    ) -> List[Token]:
        """Generate top-k tokens for the next token prediction."""
        raise NotImplementedError

    @abc.abstractmethod
    async def generate_inputs_prob(
        self, text: str, history: Optional[List[str]] = None, **extra: Any
    ) -> List[Token]:
        """Generate probabilities for each token in the input."""
        raise NotImplementedError

    @staticmethod
    def filter_think_tags(text: str, think_tag: str = "think") -> str:
        """
        Remove <think> tags from the text.
        - If the text contains <think> and </think>, it removes everything between them and the tags themselves.
        - If the text contains only </think>, it removes content before the tag.
        """
        paired_pattern = re.compile(rf"<{think_tag}>.*?</{think_tag}>", re.DOTALL)
        filtered = paired_pattern.sub("", text)

        orphan_pattern = re.compile(rf"^.*?</{think_tag}>", re.DOTALL)
        filtered = orphan_pattern.sub("", filtered)

        filtered = filtered.strip()
        return filtered if filtered else text.strip()

    def shutdown(self) -> None:
        """Shutdown the LLM engine if applicable."""

    def restart(self) -> None:
        """Reinitialize the LLM engine if applicable."""

def get_top_response_tokens(response: openai.ChatCompletion) -> List[Token]:
    token_logprobs = response.choices[0].logprobs.content
    tokens = []
    for token_prob in token_logprobs:
        prob = math.exp(token_prob.logprob)
        candidate_tokens = [
            Token(t.token, math.exp(t.logprob)) for t in token_prob.top_logprobs
        ]
        token = Token(token_prob.token, prob, top_candidates=candidate_tokens)
        tokens.append(token)
    return tokens

class OpenAIClient(BaseLLMWrapper):
    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        api_version: Optional[str] = None,
        json_mode: bool = False,
        seed: Optional[int] = None,
        topk_per_token: int = 5,  # number of topk tokens to generate for each token
        request_limit: bool = False,
        rpm: Optional[RPM] = None,
        tpm: Optional[TPM] = None,
        backend: str = "openai_api",
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.model = model
        self.api_key = api_key
        self.api_version = api_version # required for Azure OpenAI
        self.base_url = base_url
        self.json_mode = json_mode
        self.seed = seed
        self.topk_per_token = topk_per_token

        self.token_usage: list = []
        self.request_limit = request_limit
        self.rpm = rpm or RPM()
        self.tpm = tpm or TPM()

        assert (
            backend in ("openai_api", "azure_openai_api")
        ), f"Unsupported backend '{backend}'. Use 'openai_api' or 'azure_openai_api'."
        self.backend = backend

        self.__post_init__()

    def __post_init__(self):

        api_name = self.backend.replace("_", " ")
        assert self.api_key is not None, f"Please provide api key to access {api_name}."
        if self.backend == "openai_api":
            self.client = AsyncOpenAI(
                api_key=self.api_key or "dummy", base_url=self.base_url
            )
        elif self.backend == "azure_openai_api":
            assert self.api_version is not None, f"Please provide api_version for {api_name}."
            assert self.base_url is not None, f"Please provide base_url for {api_name}."
            self.client = AsyncAzureOpenAI(
                api_key=self.api_key,
                azure_endpoint=self.base_url,
                api_version=self.api_version,
                azure_deployment=self.model,
            )
        else:
            raise ValueError(f"Unsupported backend {self.backend}. Use 'openai_api' or 'azure_openai_api'.")

    def _pre_generate(self, text: str, history: List[str]) -> Dict:
        kwargs = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }
        if self.seed:
            kwargs["seed"] = self.seed
        if self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": text})

        if history:
            assert len(history) % 2 == 0, "History should have even number of elements."
            messages = history + messages

        kwargs["messages"] = messages
        return kwargs

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(
            (RateLimitError, APIConnectionError, APITimeoutError)
        ),
    )
    async def generate_topk_per_token(
        self,
        text: str,
        history: Optional[List[str]] = None,
        **extra: Any,
    ) -> List[Token]:
        kwargs = self._pre_generate(text, history)
        if self.topk_per_token > 0:
            kwargs["logprobs"] = True
            kwargs["top_logprobs"] = self.topk_per_token

        # Limit max_tokens to 1 to avoid long completions
        kwargs["max_tokens"] = 1

        completion = await self.client.chat.completions.create(  # pylint: disable=E1125
            model=self.model, **kwargs
        )

        tokens = get_top_response_tokens(completion)

        return tokens

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(
            (RateLimitError, APIConnectionError, APITimeoutError)
        ),
    )
    async def generate_answer(
        self,
        text: str,
        history: Optional[List[str]] = None,
        **extra: Any,
    ) -> str:
        kwargs = self._pre_generate(text, history)

        prompt_tokens = 0
        for message in kwargs["messages"]:
            prompt_tokens += len(self.tokenizer.encode(message["content"]))
        estimated_tokens = prompt_tokens + kwargs["max_tokens"]

        if self.request_limit:
            await self.rpm.wait(silent=True)
            await self.tpm.wait(estimated_tokens, silent=True)

        completion = await self.client.chat.completions.create(  # pylint: disable=E1125
            model=self.model, **kwargs
        )
        if hasattr(completion, "usage"):
            self.token_usage.append(
                {
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "total_tokens": completion.usage.total_tokens,
                }
            )
        return self.filter_think_tags(completion.choices[0].message.content)

    async def generate_inputs_prob(
        self, text: str, history: Optional[List[str]] = None, **extra: Any
    ) -> List[Token]:
        """Generate probabilities for each token in the input."""
        raise NotImplementedError
