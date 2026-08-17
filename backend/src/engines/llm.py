"""LLM client (OpenAI-compatible chat completions) — outline + chat/guide.

Uses the resolved provider config per request (base_url, model, api_key). In lite
mode that is the global OpenRouter config. Two surfaces:
- `talking_points`: CONTROLLED JSON prompt for governed outline building.
- `chat`: a generic grounded completion reused by chat-with-sources and the guide.
A per-call `model` override lets the Studio model dropdown pick a model per request.

Extends `EngineClient`, so it inherits the same timeout, bounded backoff on 5xx/429,
and circuit breaker as the other engines. Because the provider is resolved per request
rather than at construction, calls use absolute URLs and per-request auth headers —
httpx leaves an absolute URL untouched by the client's `base_url`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.errors import EngineError
from ..core.logging import get_logger
from ..deck.catalog import CatalogLlmResult
from ..deck.plan import PlanLlmResult
from ..outline.builder import FreeformOutlineLlmResult, LlmResult
from .base import EngineClient

logger = get_logger("orchestrator.llm")

# Operator-facing readings of the provider's non-retryable failures. These reach the
# log only — the client-facing message stays opaque (core/errors.py no-leak posture).
# Without them, a billing problem and a typo in the model slug are the same string.
_FAILURE_HINTS = {
    400: "LLM provider rejected the request payload",
    401: "LLM provider rejected the API key",
    402: "LLM provider account has insufficient credit",
    403: "LLM provider denied access to this model",
    404: "Model slug not found — check the configured model",
    413: "Prompt exceeded the provider's size limit",
}


@dataclass
class ChatAnswer:
    text: str
    tokens_in: int
    tokens_out: int
    # True when the provider stopped because `max_tokens` was hit
    # (`finish_reason == "length"`), not because it had nothing more to say. The
    # provider always reports this; discarding it made a cut-off answer render
    # identically to a complete one.
    truncated: bool = False


class LlmClient(EngineClient):
    def __init__(self, *, client: httpx.AsyncClient | None = None):
        # base_url is empty by design: the provider comes from the tenant's config on
        # every call, so requests carry absolute URLs. `client` keeps the test seam.
        super().__init__(name="llm", base_url="", client=client)

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
        resp = await self.request(
            "POST",
            f"{base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": settings.public_base_url,
                "X-Title": settings.app_name,
            },
        )

        if resp.status_code >= 400:
            self._log_failure(resp, model=model)
            raise EngineError("LLM provider request failed.")
        return resp.json()

    @staticmethod
    def _log_failure(resp: httpx.Response, *, model: str) -> None:
        """Record what actually went wrong, server-side, with enough to act on."""
        logger.error(
            "llm_request_failed",
            extra={
                "status_code": resp.status_code,
                "hint": _FAILURE_HINTS.get(
                    resp.status_code, "LLM provider returned an error"
                ),
                "model": model,
                "body_snippet": (getattr(resp, "text", "") or "")[:200],
            },
        )

    @staticmethod
    def _extract_json_content(body: dict[str, Any], *, model: str, error_message: str) -> Any:
        """`choices[0].message.content` -> parsed JSON, for every strict-JSON
        call (`talking_points`, `draft_outline`, `catalog_template`,
        `plan_deck`) -- centralised because the failure mode this pipeline
        actually hit in production (2026-08-16, `moonshotai/kimi-k3` via
        OpenRouter) was a 200 OK response with `content: null`: the
        completion's token budget was spent before any visible content was
        emitted -- most likely a reasoning-capable model's hidden "thinking"
        tokens consuming the whole budget on a large prompt (LD-2's ~12k
        token template dump). `_log_failure` only fires on HTTP >= 400, which
        this is not, so that failure was otherwise invisible without a shell
        into the worker container. Logging `finish_reason`/token usage/a
        reasoning-field length here means the NEXT occurrence is diagnosable
        from logs alone.
        """
        try:
            choice = body["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError) as exc:
            raise EngineError(error_message) from exc

        content = message.get("content")
        if not content:
            usage = body.get("usage", {})
            reasoning_field = message.get("reasoning") or message.get("reasoning_content") or ""
            logger.error(
                "llm_response_content_empty",
                extra={
                    "model": model,
                    "finish_reason": choice.get("finish_reason"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "reasoning_field_length": len(str(reasoning_field)),
                },
            )
            raise EngineError(error_message)

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise EngineError(error_message) from exc

    async def talking_points(
        self,
        *,
        section_ids: list[str],
        context: list[dict[str, Any]],
        profile: dict[str, Any],
        provider_config: dict[str, Any],
    ) -> LlmResult:
        settings = get_settings()
        model = provider_config.get("model")
        body = await self._complete(
            messages=_build_messages(section_ids, context, profile),
            provider_config=provider_config,
            temperature=settings.outline_llm_temperature,
            max_tokens=settings.outline_llm_max_tokens,
            response_format={"type": "json_object"},
        )
        data = self._extract_json_content(
            body, model=model, error_message="LLM returned an unparseable outline response."
        )

        usage = body.get("usage", {})
        return LlmResult(
            points_by_section=_coerce_points(data, section_ids),
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )

    async def draft_outline(
        self,
        *,
        content: str,
        tone: str,
        density: str,
        n_slides_hint: int | None,
        language: str,
        provider_config: dict[str, Any],
    ) -> FreeformOutlineLlmResult:
        """One call: propose outline structure AND wording (DG-1's freeform path).

        Unlike `talking_points`, there are no fixed section ids to fill in -- the
        model returns its own titles, so the parse has to tolerate a shape it did
        not get to negotiate (missing/blank titles, a non-list `bullets`) rather
        than assume compliance the way the governed prompt can.
        """
        settings = get_settings()
        model = provider_config.get("model")
        body = await self._complete(
            messages=_build_freeform_outline_messages(
                content, tone, density, n_slides_hint, language
            ),
            provider_config=provider_config,
            temperature=settings.outline_llm_temperature,
            max_tokens=settings.outline_llm_max_tokens,
            response_format={"type": "json_object"},
        )
        data = self._extract_json_content(
            body, model=model, error_message="LLM returned an unparseable outline draft."
        )
        try:
            raw_sections = data["sections"]
            if not isinstance(raw_sections, list):
                raise TypeError("`sections` must be a list")
        except (KeyError, TypeError) as exc:
            raise EngineError("LLM returned an unparseable outline draft.") from exc

        usage = body.get("usage", {})
        return FreeformOutlineLlmResult(
            sections=[s for s in raw_sections if isinstance(s, dict)],
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )

    async def catalog_template(
        self,
        *,
        slide_dump_text: str,
        slide_indexes: list[int],
        provider_config: dict[str, Any],
        model_override: str | None = None,
    ) -> CatalogLlmResult:
        """LD-2 -- one batch of `deck/dump.py` text -> raw per-slide designs.

        One-time-per-template cost (`ASSESSMENT-LLM-DECK-PLANNING.md` §4): the
        best model in the tenant's routing, not the cheapest, since this call
        amortises across every deck the template ever renders.
        """
        settings = get_settings()
        model = model_override or provider_config.get("model")
        body = await self._complete(
            messages=_build_catalog_messages(slide_dump_text=slide_dump_text),
            provider_config=provider_config,
            temperature=settings.deck_catalog_llm_temperature,
            max_tokens=settings.deck_catalog_llm_max_tokens,
            response_format={"type": "json_object"},
            model_override=model_override,
        )
        data = self._extract_json_content(
            body, model=model, error_message="LLM returned an unparseable design catalog."
        )
        try:
            raw_designs = data["designs"]
            if not isinstance(raw_designs, list):
                raise TypeError("`designs` must be a list")
        except (KeyError, TypeError) as exc:
            raise EngineError("LLM returned an unparseable design catalog.") from exc

        usage = body.get("usage", {})
        return CatalogLlmResult(
            raw_designs=[d for d in raw_designs if isinstance(d, dict)],
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )

    async def plan_deck(
        self,
        *,
        content: str,
        catalog: list[dict[str, Any]],
        n_slides_hint: int | None,
        tone: str,
        density: str,
        language: str,
        provider_config: dict[str, Any],
        model_override: str | None = None,
    ) -> PlanLlmResult:
        """LD-6 -- catalog + content -> one call -> the whole `DeckPlan`.

        Replaces the old role/budget-based `plan_deck` (RM-6) now that
        `generation/service.py` is cut over to the catalog pipeline (LD-9);
        the old method and its layout-matching counterpart (`match_layout`,
        RM-7) are deleted alongside `deck/planner.py`/`deck/matcher.py`
        (LD-11) -- there is no separate layout-matching call anymore because
        design selection happens in this SAME call as content.

        Reuses the deck-content settings (`deck_plan_llm_*`) -- same task,
        same quality bar (Bahasa Indonesia fluency, budget compliance,
        strict JSON).
        """
        settings = get_settings()
        model = model_override or provider_config.get("model")
        body = await self._complete(
            messages=_build_catalog_plan_messages(
                content=content,
                catalog=catalog,
                n_slides_hint=n_slides_hint,
                tone=tone,
                density=density,
                language=language,
            ),
            provider_config=provider_config,
            temperature=settings.deck_plan_llm_temperature,
            max_tokens=settings.deck_plan_llm_max_tokens,
            response_format={"type": "json_object"},
            model_override=model_override,
        )
        data = self._extract_json_content(
            body, model=model, error_message="LLM returned an unparseable deck plan."
        )
        try:
            raw_slides = data["slides"]
            if not isinstance(raw_slides, list):
                raise TypeError("`slides` must be a list")
        except (KeyError, TypeError) as exc:
            raise EngineError("LLM returned an unparseable deck plan.") from exc

        notes_raw = data.get("notes")
        notes = (str(notes_raw).strip() or None) if notes_raw is not None else None
        usage = body.get("usage", {})
        return PlanLlmResult(
            raw_slides=[s for s in raw_slides if isinstance(s, dict)],
            notes=notes,
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
            choice = body["choices"][0]
            text = choice["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise EngineError("LLM returned an unparseable chat response.") from exc

        usage = body.get("usage", {})
        return ChatAnswer(
            text=text.strip(),
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            truncated=choice.get("finish_reason") == "length",
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


def _build_freeform_outline_messages(
    content: str,
    tone: str,
    density: str,
    n_slides_hint: int | None,
    language: str,
) -> list[dict[str, str]]:
    target = (
        f"Aim for roughly {n_slides_hint} sections."
        if n_slides_hint
        else "Choose the number of sections the content actually supports -- "
        "typically between 4 and 12. Do not pad or truncate to hit a round number."
    )
    system = (
        "You draft a presentation outline directly from source material. There is "
        "no fixed structure to fill in -- propose the sections yourself, in the "
        f"order they should appear. {target} "
        f"Tone: {tone}. Verbosity: {density}. Write in {language}. "
        'Return STRICT JSON: {"sections": [{"title": str, "bullets": [str, ...]}, ...]}. '
        "No prose outside the JSON."
    )
    user = f"Source material:\n{content}\n\nReturn the JSON outline."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_catalog_messages(*, slide_dump_text: str) -> list[dict[str, str]]:
    """LD-2's prompt. Asks the model for exactly two things it is actually
    good at -- recognition (role, which shapes matter, what they're for) --
    and nothing it is unreliable at: `capacity` and `char_budget` are computed
    in `deck/catalog.py` from the shapes the model names, never requested
    here (module docstring, `deck/catalog.py`)."""
    system = (
        "You catalogue a PowerPoint template's slides as a reusable design "
        "vocabulary for a slide-CLONING renderer -- slides are never rebuilt, "
        "only reused wholesale with their text replaced. For EACH slide given "
        "below, identify:\n"
        "1. `role` -- a short label for what kind of slide this is, e.g. "
        "cover, divider, two_key_points, three_cards, nine_points, timeline, "
        "matrix, closing, table, chart, logo_library.\n"
        "2. `anchors` -- every shape whose text content should be REPLACED "
        "when this design is reused for new content. For each: `anchor_id` "
        "(the shape id given in the dump, as a string) and `purpose` -- one "
        "of title, subtitle, body, item_<N>_title, item_<N>_body, "
        "visual_caption, other. Use item_1_title/item_1_body, "
        "item_2_title/item_2_body, etc. for repeated groups such as cards, "
        "timeline entries or bullet rows, numbering them in reading order "
        "(left-to-right, top-to-bottom). Do NOT invent an anchor for a shape "
        "with no text, a page number, a static logo/decoration, or a label "
        "that must stay fixed (e.g. a chart's axis unit) -- only shapes whose "
        "CONTENT changes per use.\n"
        "3. `usable` -- false if this slide has no anchor a renderer could "
        "fill (pure decoration, an image library, a divider with nothing to "
        "replace), with a short `reason` explaining why.\n"
        'Return STRICT JSON: {"designs": [{"slide_index": int, "role": str, '
        '"usable": bool, "reason": str|null, "anchors": [{"anchor_id": str, '
        '"purpose": str}, ...]}, ...]} -- exactly one entry per SLIDE given, '
        "in the order given, referencing that slide's own `slide_index`. No "
        "prose outside the JSON."
    )
    user = f"{slide_dump_text}\n\nReturn the JSON catalog for every SLIDE above."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_catalog_plan_messages(
    *,
    content: str,
    catalog: list[dict[str, Any]],
    n_slides_hint: int | None,
    tone: str,
    density: str,
    language: str,
) -> list[dict[str, str]]:
    """LD-6's prompt. System message (the catalog description) first, content
    last -- same cache-friendly ordering as `_build_deck_plan_messages`
    (`COST-AND-MODEL-STRATEGY.md` §4.3): the catalog brief is byte-identical
    across every generation against the same template, so a provider's
    prompt cache can hit on it; only the source content changes per call."""
    designs_desc = (
        "\n".join(
            f"- {d['design_id']} (role={d['role']}, capacity={d['capacity']}): "
            + (
                ", ".join(
                    f"{a['anchor_id']}={a['purpose']}"
                    + (f" <= {a['char_budget']} chars" if a.get("char_budget") else "")
                    for a in d["anchors"]
                )
                or "no anchors"
            )
            for d in catalog
        )
        or "(no usable designs -- this should not happen; cataloguing should have caught this)"
    )
    target = (
        f"Produce roughly {n_slides_hint} slides."
        if n_slides_hint
        else "Choose the number of slides the content actually supports -- "
        "typically between 4 and 16. Do not pad or truncate to hit a round number."
    )
    system = (
        "You plan a slide deck by choosing which of this template's "
        "ALREADY-DESIGNED slides to reuse for each piece of content, and what "
        "to write into it. You never invent layout, colour or font -- a "
        "separate renderer clones the chosen design exactly as it was "
        "designed and fills only the anchors you specify; describing "
        "appearance is wasted effort and will be ignored.\n"
        f"Available designs:\n{designs_desc}\n"
        "For each slide you plan: `design_id` must be one of the ids above, "
        "exactly. `anchor_texts` maps an anchor_id (from that SAME design) to "
        "the text it should hold -- write to every anchor the design offers "
        "that your content has something for, and never invent an anchor_id "
        "the design does not list. Respect the character budget on anchors "
        "that have one -- it is the physical space the shape occupies, not a "
        "suggestion; text beyond it will be cut. A design may be reused any "
        "number of times: if your content for one section has more items "
        "than a single use of a design can hold, split it across repeated "
        'uses of the SAME design_id, and suffix the continuation slide\'s '
        'title anchor\'s text with " (lanjutan)". Order the slides list in '
        f"the order the deck should read. {target} "
        f"Tone: {tone}. Verbosity: {density}. Write in {language}. "
        'Return STRICT JSON: {"slides": [{"design_id": str, "anchor_texts": '
        '{"<anchor_id>": str, ...}}, ...], "notes": str|null}. No prose '
        "outside the JSON."
    )
    user = f"Source content:\n{content}\n\nReturn the JSON deck plan."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]




def _coerce_points(data: dict[str, Any], section_ids: list[str]) -> dict[str, list[str]]:
    points: dict[str, list[str]] = {}
    for sid in section_ids:
        value = data.get(sid, [])
        if isinstance(value, str):
            value = [value]
        points[sid] = [str(v) for v in value if v]
    return points
