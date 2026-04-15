import json
from abc import ABC, abstractmethod
from types import NoneType
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from pydantic.fields import PydanticUndefined

from app.core.config import Settings


T = TypeVar("T", bound=BaseModel)


class BaseLLMProvider(ABC):
    @abstractmethod
    def invoke_structured(self, system_prompt: str, user_prompt: str, schema: type[T]) -> T:
        raise NotImplementedError

    @abstractmethod
    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class OpenAIProvider(BaseLLMProvider):
    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        kwargs: dict = dict(model=model_name, api_key=api_key, temperature=0)
        if base_url:
            kwargs["base_url"] = base_url
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        self._client = ChatOpenAI(**kwargs)

    def invoke_structured(self, system_prompt: str, user_prompt: str, schema: type[T]) -> T:
        structured = self._client.with_structured_output(schema)
        return structured.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )

    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )
        return str(response.content)


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek Chat — OpenAI-compatible API, no extra packages needed."""

    _BASE_URL = "https://api.deepseek.com/v1"

    def __init__(self, model_name: str, api_key: str, max_tokens: int | None = None) -> None:
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            base_url=self._BASE_URL,
            max_tokens=max_tokens,
        )


class MockLLMProvider(BaseLLMProvider):
    def invoke_structured(self, system_prompt: str, user_prompt: str, schema: type[T]) -> T:
        try:
            payload = json.loads(user_prompt)
        except json.JSONDecodeError:
            payload = {"summary": user_prompt}

        try:
            return schema.model_validate(payload)
        except Exception:
            fallback = self._build_fallback_payload(payload, schema)
            return schema.model_validate(fallback)

    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        return f"{system_prompt}\n\n{user_prompt}"

    def _build_fallback_payload(self, payload: dict, schema: type[T]) -> dict:
        fallback: dict[str, object] = {}
        for field_name, field_info in schema.model_fields.items():
            if field_name in payload:
                fallback[field_name] = payload[field_name]
                continue

            if field_info.default is not PydanticUndefined:
                fallback[field_name] = field_info.default
                continue

            annotation = field_info.annotation
            fallback[field_name] = self._fallback_value(field_name, annotation, payload)
        return fallback

    def _fallback_value(self, field_name: str, annotation, payload: dict) -> object:
        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())

        if origin is list:
            return []
        if origin is dict:
            return {}
        if origin is NoneType:
            return None
        if origin is not None and NoneType in args:
            non_none_args = [arg for arg in args if arg is not NoneType]
            if len(non_none_args) == 1:
                return self._fallback_value(field_name, non_none_args[0], payload)

        if annotation in {float, int}:
            return 0.42 if annotation is float else 0
        if annotation is bool:
            return False
        if annotation is str:
            if field_name == "jurisdiction":
                return payload.get("jurisdiction", "czechia")
            if field_name == "domain":
                return payload.get("domain", "mixed")
            if field_name == "answer_type":
                return payload.get("answer_type", "semantic_explanation")
            if field_name == "summary":
                return payload.get("summary", "Mock provider synthesized an evidence-grounded response.")
            if field_name == "explanation":
                return payload.get("explanation", payload.get("summary", "Mock explanation generated from retrieved chunks."))
            if field_name == "answer":
                return payload.get("answer", payload.get("summary", "Mock answer generated from retrieved chunks."))
            if field_name == "query":
                return payload.get("query", "")
            return payload.get(field_name, "")

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return self._build_fallback_payload(payload, annotation)

        literals = getattr(annotation, "__args__", ())
        if literals and all(isinstance(item, str) for item in literals):
            return literals[0]

        return payload.get(field_name)


def build_llm_provider(settings: Settings) -> BaseLLMProvider:
    provider = settings.llm_provider.lower()
    api_key = settings.llm_api_key
    max_tokens = settings.llm_max_output_tokens
    if provider == "deepseek" and api_key:
        return DeepSeekProvider(
            model_name=settings.llm_model,
            api_key=api_key,
            max_tokens=max_tokens,
        )
    if provider == "openai" and api_key:
        return OpenAIProvider(
            model_name=settings.llm_model,
            api_key=api_key,
            base_url=settings.openai_base_url,
            max_tokens=max_tokens,
        )
    return MockLLMProvider()
