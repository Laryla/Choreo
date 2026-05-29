"""
PatchedChatOpenAI：修复思考内容在多轮对话中的回传问题。

问题背景
--------
DeepSeek reasoner 等思考模型在 OpenAI 兼容网关下，要求每轮助手消息把
原来返回的 reasoning_content 原样回传给下一轮请求。
标准 langchain_openai.ChatOpenAI 只序列化标准字段，会静默丢掉这个字段，
导致多轮对话时 400 错误或思考链断裂。

同理，Gemini 思考模型通过 OpenAI 兼容网关时需要回传 thought_signature。

此模块通过重写 _get_request_payload / _convert_chunk_to_generation_chunk /
_create_chat_result 三个方法来修复上述问题。

用法（config.yaml）
------------------
- name: deepseek-reasoner
  use: choreo.models.patched_openai:PatchedChatOpenAI
  model: deepseek-reasoner
  api_key: $DEEPSEEK_API_KEY
  base_url: https://api.deepseek.com/v1
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI


class PatchedChatOpenAI(ChatOpenAI):
    """ChatOpenAI，修复 reasoning_content / thought_signature 在多轮对话中丢失的问题。"""

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        original_messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        payload_messages = payload.get("messages", [])

        if len(payload_messages) == len(original_messages):
            for payload_msg, orig_msg in zip(payload_messages, original_messages):
                if payload_msg.get("role") == "assistant" and isinstance(orig_msg, AIMessage):
                    _restore_thought_signature(payload_msg, orig_msg)
                    _restore_reasoning_content(payload_msg, orig_msg)
        else:
            ai_messages = [m for m in original_messages if isinstance(m, AIMessage)]
            assistant_payloads = [m for m in payload_messages if m.get("role") == "assistant"]
            for payload_msg, ai_msg in zip(assistant_payloads, ai_messages):
                _restore_thought_signature(payload_msg, ai_msg)
                _restore_reasoning_content(payload_msg, ai_msg)

        return payload

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        """流式输出时把 reasoning_content 保存到 additional_kwargs。"""
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation_chunk is None:
            return None

        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices", [])
        choice = choices[0] if choices else {}
        delta = choice.get("delta") if isinstance(choice, dict) else None
        reasoning = _extract_reasoning(delta if isinstance(delta, dict) else None)
        if reasoning and isinstance(generation_chunk.message, AIMessageChunk):
            generation_chunk.message = _append_reasoning(generation_chunk.message, reasoning)
        return generation_chunk

    def _create_chat_result(
        self,
        response: dict | Any,
        generation_info: dict | None = None,
    ) -> ChatResult:
        """非流式输出时把 reasoning_content 保存到 additional_kwargs。"""
        result = super()._create_chat_result(response, generation_info)
        response_dict = response if isinstance(response, dict) else response.model_dump()
        choices = response_dict.get("choices", [])

        generations: list[ChatGeneration] = []
        for idx, generation in enumerate(result.generations):
            message = generation.message
            choice = choices[idx] if idx < len(choices) else {}
            choice_msg = choice.get("message", {}) if isinstance(choice, dict) else {}
            reasoning = _extract_reasoning(choice_msg if isinstance(choice_msg, dict) else None)
            if reasoning and isinstance(message, AIMessage):
                message = _append_reasoning(message, reasoning)
                generation = ChatGeneration(
                    message=message,
                    generation_info=generation.generation_info,
                )
            generations.append(generation)

        return ChatResult(generations=generations, llm_output=result.llm_output)


# ── 内部工具函数 ────────────────────────────────────────────────────

def _restore_thought_signature(payload_msg: dict, orig_msg: AIMessage) -> None:
    """把 Gemini 思考签名重新注入 payload 的 tool_calls 里。"""
    raw_tcs: list[dict] = orig_msg.additional_kwargs.get("tool_calls") or []
    payload_tcs: list[dict] = payload_msg.get("tool_calls") or []
    if not raw_tcs or not payload_tcs:
        return
    raw_by_id = {tc["id"]: tc for tc in raw_tcs if tc.get("id")}
    for idx, ptc in enumerate(payload_tcs):
        rtc = raw_by_id.get(ptc.get("id", "")) or (raw_tcs[idx] if idx < len(raw_tcs) else None)
        if rtc:
            sig = rtc.get("thought_signature") or rtc.get("thoughtSignature")
            if sig:
                ptc["thought_signature"] = sig


def _restore_reasoning_content(payload_msg: dict, orig_msg: AIMessage) -> None:
    """把 DeepSeek reasoning_content 回传给下一轮请求。"""
    rc = orig_msg.additional_kwargs.get("reasoning_content")
    if rc is not None:
        payload_msg["reasoning_content"] = rc


def _extract_reasoning(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    rc = payload.get("reasoning_content")
    return rc if isinstance(rc, str) and rc else None


def _append_reasoning(message: AIMessage | AIMessageChunk, reasoning: str) -> AIMessage | AIMessageChunk:
    kwargs = dict(message.additional_kwargs)
    existing = kwargs.get("reasoning_content", "")
    if isinstance(existing, str) and existing and reasoning not in existing:
        kwargs["reasoning_content"] = existing + reasoning
    else:
        kwargs["reasoning_content"] = reasoning
    return message.model_copy(update={"additional_kwargs": kwargs})
