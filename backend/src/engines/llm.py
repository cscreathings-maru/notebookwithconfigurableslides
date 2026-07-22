"""LLM client (OpenAI-compatible chat completions) — outline + chat/guide.

Uses the resolved provider config per request (base_url, model, api_key). In lite
mode that is the global OpenRouter config. Two surfaces:
- `talking_points`: CONTROLLED JSON prompt for governed outline building.
- `chat`: a generic grounded completion reused by chat-with-sources and the guide.
A per-call `model` override lets the Studio model dropdown pick a model per request.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.errors import EngineError
from ..core.logging import get_logger
from ..outline.builder import LlmResult

logger = get_logger("orchestrator.llm")


@dataclass
class ChatAnswer:
    text: str
    tokens_in: int
    tokens_out: int


class LlmClient:
    def __init__(self, *, client: httpx.AsyncClient | None = None):
        self._client = client  # injectable for tests

    async def _complete(
        self,
        *,
        messages: list[dict[str, str]],
        provider_config: dict[str, Any],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, str] | None = None,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        """Issue one chat completion and return the raw response body."""
        settings = get_settings()
        base_url = provider_config.get("base_url")
        model = model_override or provider_config.get("model")
        api_key = provider_config.get("api_key")
        if not (base_url and model and api_key):
            raise EngineError("LLM provider config is incomplete.")

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        # OpenRouter uses HTTP-Referer / X-Title for app attribution; other
        # OpenAI-compatible providers simply ignore them.
        client = self._client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=settings.engine_timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": settings.public_base_url,
                "X-Title": settings.app_name,
            },
        )
        owns = self._client is None
        try:
            resp = await client.post("/chat/completions", json=payload)
        finally:
            if owns:
                await client.aclose()

        if resp.status_code >= 400:
            raise EngineError("LLM provider request failed.")
        return resp.json()

    async def talking_points(
        self,
        *,
        section_ids: list[str],
        context: list[dict[str, Any]],
        profile: dict[str, Any],
        provider_config: dict[str, Any],
    ) -> LlmResult:
        settings = get_settings()
        body = await self._complete(
            messages=_build_messages(section_ids, context, profile),
            provider_config=provider_config,
            temperature=settings.outline_llm_temperature,
            max_tokens=settings.outline_llm_max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            content = body["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise EngineError("LLM returned an unparseable outline response.") from exc

        usage = body.get("usage", {})
        return LlmResult(
            points_by_section=_coerce_points(data, section_ids),
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )

    async def chat(
        self,
        *,
        system: str,
        user: str,
        provider_config: dict[str, Any],
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1200,
        model_override: str | None = None,
    ) -> ChatAnswer:
        """Generic grounded completion — returns plain text plus token usage."""
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user})

        body = await self._complete(
            messages=messages,
            provider_config=provider_config,
            temperature=temperature,
            max_tokens=max_tokens,
            model_override=model_override,
        )
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise EngineError("LLM returned an unparseable chat response.") from exc

        usage = body.get("usage", {})
        return ChatAnswer(
            text=text.strip(),
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )


def _build_messages(
    section_ids: list[str], context: list[dict[str, Any]], profile: dict[str, Any]
) -> list[dict[str, str]]:
    grounding = "\n".join(f"- {c.get('text', '')}" for c in context) or "(no analysis context)"
    system = (
        "You write concise, on-brand presentation talking points. "
        "You MUST return strict JSON mapping each given section id to an array of "
        "short bullet strings. Do not invent or reorder sections. "
        f"Audience: {profile.get('audience')}. Tone: {profile.get('tone')}. "
        f"Verbosity: {profile.get('verbosity')}. Language: {profile.get('language')}. "
        f"{profile.get('prompt_config', {}).get('system', '') if isinstance(profile.get('prompt_config'), dict) else ''}"
    )
    user = (
        f"Section ids (fixed order): {json.dumps(section_ids)}\n"
        f"Grounding facts:\n{grounding}\n\n"
        'Return JSON like {"section_id": ["point", ...], ...} for exactly these ids.'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _coerce_points(data: dict[str, Any], section_ids: list[str]) -> dict[str, list[str]]:
    points: dict[str, list[str]] = {}
    for sid in section_ids:
        value = data.get(sid, [])
        if isinstance(value, str):
            value = [value]
        points[sid] = [str(v) for v in value if v]
    return points
