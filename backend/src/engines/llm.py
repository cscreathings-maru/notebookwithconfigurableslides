"""LLM client for outline building (OpenAI-compatible chat completions).

Uses the tenant's BYOK provider config per request (base_url, model, api_key). The
prompt is CONTROLLED: it asks only for talking points per fixed section id, as JSON,
at low temperature — the model never decides structure. Returns talking points plus
token usage for metering.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.errors import EngineError
from ..core.logging import get_logger
from ..outline.builder import LlmResult

logger = get_logger("orchestrator.llm")


class LlmClient:
    def __init__(self, *, client: httpx.AsyncClient | None = None):
        self._client = client  # injectable for tests

    async def talking_points(
        self,
        *,
        section_ids: list[str],
        context: list[dict[str, Any]],
        profile: dict[str, Any],
        provider_config: dict[str, Any],
    ) -> LlmResult:
        settings = get_settings()
        base_url = provider_config.get("base_url")
        model = provider_config.get("model")
        api_key = provider_config.get("api_key")
        if not (base_url and model and api_key):
            raise EngineError("Tenant LLM provider config is incomplete.")

        messages = _build_messages(section_ids, context, profile)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": settings.outline_llm_temperature,
            "max_tokens": settings.outline_llm_max_tokens,
            "response_format": {"type": "json_object"},
        }

        client = self._client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=settings.engine_timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        owns = self._client is None
        try:
            resp = await client.post("/chat/completions", json=payload)
        finally:
            if owns:
                await client.aclose()

        if resp.status_code >= 400:
            raise EngineError("LLM provider request failed.")

        body = resp.json()
        try:
            content = body["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise EngineError("LLM returned an unparseable outline response.") from exc

        usage = body.get("usage", {})
        points = _coerce_points(data, section_ids)
        return LlmResult(
            points_by_section=points,
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
