"""T-2.3: the LLM must be as resilient and as diagnosable as the other engines.

`LlmClient` called httpx directly -- no retry, no backoff, no circuit breaker, unlike
`OpenNotebookClient`. Every failure collapsed into the single
string "LLM provider request failed.", so an operator could not tell an expired key
from insufficient credit from a typo in the model slug.

Client-facing messages stay opaque on purpose (`core/errors.py` no-leak posture);
these tests assert the detail reaches the **log**, not the response.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from src.core.errors import EngineError
from src.engines.llm import LlmClient

PROVIDER = {
    "provider": "openrouter",
    "base_url": "https://openrouter.test/api/v1",
    "model": "anthropic/claude-3.5-sonnet",
    "api_key": "sk-or-test",
}

COMPLETION = {
    "choices": [{"message": {"content": "Revenue grew 12%."}}],
    "usage": {"prompt_tokens": 11, "completion_tokens": 7},
}


def _client(handler) -> LlmClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://unused")
    return LlmClient(client=http)


def _always(status: int, payload: dict | None = None, text: str = ""):
    """Handler returning a fixed response, recording every request it sees."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if payload is not None:
            return httpx.Response(status, json=payload)
        return httpx.Response(status, text=text)

    return handler, seen


# --------------------------------------------------------------------------
# Resilience -- inherited from EngineClient
# --------------------------------------------------------------------------


def test_llm_client_is_an_engine_client() -> None:
    from src.engines.base import EngineClient

    assert issubclass(LlmClient, EngineClient)
    assert LlmClient().breaker is not None


async def test_chat_succeeds_and_reports_token_usage() -> None:
    # Arrange
    handler, seen = _always(200, COMPLETION)

    # Act
    answer = await _client(handler).chat(
        system="s", user="u", provider_config=PROVIDER
    )

    # Assert
    assert answer.text == "Revenue grew 12%."
    assert (answer.tokens_in, answer.tokens_out) == (11, 7)
    assert len(seen) == 1


async def test_request_targets_the_per_request_provider_base_url() -> None:
    """The provider is resolved per call, so the URL must not come from the client."""
    # Arrange
    handler, seen = _always(200, COMPLETION)

    # Act
    await _client(handler).chat(system="s", user="u", provider_config=PROVIDER)

    # Assert
    assert str(seen[0].url) == "https://openrouter.test/api/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer sk-or-test"


async def test_rate_limiting_is_retried() -> None:
    # Arrange
    handler, seen = _always(429, text="slow down")

    # Act
    with pytest.raises(EngineError):
        await _client(handler).chat(system="s", user="u", provider_config=PROVIDER)

    # Assert -- retried, not given up on after one attempt
    assert len(seen) > 1


async def test_server_errors_are_retried() -> None:
    # Arrange
    handler, seen = _always(503, text="upstream down")

    # Act
    with pytest.raises(EngineError):
        await _client(handler).chat(system="s", user="u", provider_config=PROVIDER)

    # Assert
    assert len(seen) > 1


async def test_auth_failure_is_not_retried() -> None:
    """A bad key will be bad next time too; retrying only delays the diagnosis."""
    # Arrange
    handler, seen = _always(401, text="invalid api key")

    # Act
    with pytest.raises(EngineError):
        await _client(handler).chat(system="s", user="u", provider_config=PROVIDER)

    # Assert
    assert len(seen) == 1


async def test_retry_is_logged_with_its_status(caplog) -> None:
    # Arrange
    handler, _seen = _always(429, text="slow down")

    # Act
    with caplog.at_level(logging.WARNING):
        with pytest.raises(EngineError):
            await _client(handler).chat(system="s", user="u", provider_config=PROVIDER)

    # Assert
    assert any("engine_request_retrying" in r.getMessage() for r in caplog.records)


# --------------------------------------------------------------------------
# Diagnosability -- each status names its own cause
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (401, "API key"),
        (402, "insufficient credit"),
        (404, "Model slug not found"),
        (403, "denied access"),
    ],
)
async def test_failure_status_maps_to_an_actionable_log(status, fragment, caplog) -> None:
    # Arrange
    handler, _seen = _always(status, text="provider detail")

    # Act
    with caplog.at_level(logging.ERROR):
        with pytest.raises(EngineError):
            await _client(handler).chat(system="s", user="u", provider_config=PROVIDER)

    # Assert -- the operator can tell which failure this was
    hints = [getattr(r, "hint", "") for r in caplog.records]
    assert any(fragment in h for h in hints), hints


async def test_failure_log_carries_status_model_and_body(caplog) -> None:
    # Arrange
    handler, _seen = _always(402, text="credits exhausted, top up at ...")

    # Act
    with caplog.at_level(logging.ERROR):
        with pytest.raises(EngineError):
            await _client(handler).chat(system="s", user="u", provider_config=PROVIDER)

    # Assert
    record = next(r for r in caplog.records if r.getMessage() == "llm_request_failed")
    assert record.status_code == 402
    assert record.model == PROVIDER["model"]
    assert "credits exhausted" in record.body_snippet


async def test_client_facing_message_leaks_no_provider_detail() -> None:
    """The raised message must never echo the provider's response body --
    that body routinely contains the API key, the upstream URL, or internal
    identifiers. It carries one of our OWN static hints instead.

    Asserted as a property rather than an exact string: the message became
    actionable in 2026-08-17 (an out-of-credit account previously surfaced as
    an opaque "LLM provider request failed."), and pinning the literal made
    that improvement look like a regression when it was the point.
    """
    # Arrange -- a provider body carrying a secret, on a status we have a hint for
    handler, _seen = _always(401, text="key sk-or-secret-123 is revoked")

    # Act
    with pytest.raises(EngineError) as excinfo:
        await _client(handler).chat(system="s", user="u", provider_config=PROVIDER)

    # Assert
    message = str(excinfo.value)
    assert "sk-or-secret-123" not in message
    assert "revoked" not in message, "the provider's own wording must not pass through"
    assert message == "LLM provider rejected the API key."


async def test_an_out_of_credit_account_says_so_instead_of_failing_opaquely() -> None:
    """The 2026-08-17 production failure: cataloguing died on a 402 and the
    admin's only clue was `catalog_error: "LLM provider request failed."`.
    The status is diagnostic on its own -- say what it means."""
    # Arrange
    handler, _seen = _always(
        402, text='{"error":{"message":"This request requires more credits, or fewer max_tokens."}}'
    )

    # Act
    with pytest.raises(EngineError) as excinfo:
        await _client(handler).catalog_template(
            slide_dump_text="SLIDE 0", slide_indexes=[0], provider_config=PROVIDER
        )

    # Assert
    assert str(excinfo.value) == "LLM provider account has insufficient credit."


# --------------------------------------------------------------------------
# Config and parsing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing", ["base_url", "model", "api_key"]
)
async def test_incomplete_provider_config_fails_before_any_request(missing) -> None:
    # Arrange
    handler, seen = _always(200, COMPLETION)
    config = {k: v for k, v in PROVIDER.items() if k != missing}

    # Act
    with pytest.raises(EngineError):
        await _client(handler).chat(system="s", user="u", provider_config=config)

    # Assert -- no call was made with a half-built config
    assert seen == []


async def test_model_override_wins_over_the_configured_model() -> None:
    """The Studio model dropdown depends on this."""
    # Arrange
    handler, seen = _always(200, COMPLETION)

    # Act
    await _client(handler).chat(
        system="s", user="u", provider_config=PROVIDER, model_override="openai/gpt-4o"
    )

    # Assert
    assert json.loads(seen[0].content)["model"] == "openai/gpt-4o"


async def test_history_is_sent_between_system_and_user() -> None:
    # Arrange
    handler, seen = _always(200, COMPLETION)

    # Act
    await _client(handler).chat(
        system="s",
        user="u",
        provider_config=PROVIDER,
        history=[{"role": "assistant", "content": "earlier"}],
    )

    # Assert
    roles = [m["role"] for m in json.loads(seen[0].content)["messages"]]
    assert roles == ["system", "assistant", "user"]


async def test_unparseable_chat_response_is_an_engine_error() -> None:
    # Arrange -- 200, but not the shape the contract promises
    handler, _seen = _always(200, {"unexpected": True})

    # Act / Assert
    with pytest.raises(EngineError):
        await _client(handler).chat(system="s", user="u", provider_config=PROVIDER)


async def test_talking_points_parses_json_and_requests_json_mode() -> None:
    # Arrange
    handler, seen = _always(
        200,
        {
            "choices": [{"message": {"content": json.dumps({"s1": ["a", "b"], "s2": "c"})}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 9},
        },
    )

    # Act
    result = await _client(handler).talking_points(
        section_ids=["s1", "s2"], context=[], profile={}, provider_config=PROVIDER
    )

    # Assert
    assert result.points_by_section == {"s1": ["a", "b"], "s2": ["c"]}
    assert (result.tokens_in, result.tokens_out) == (5, 9)
    assert json.loads(seen[0].content)["response_format"] == {"type": "json_object"}


async def test_talking_points_rejects_unparseable_json() -> None:
    # Arrange
    handler, _seen = _always(
        200, {"choices": [{"message": {"content": "not json at all"}}]}
    )

    # Act / Assert
    with pytest.raises(EngineError):
        await _client(handler).talking_points(
            section_ids=["s1"], context=[], profile={}, provider_config=PROVIDER
        )


# --------------------------------------------------------------------------
# `_extract_json_content` -- the 2026-08-16 production bug: a 200 OK response
# whose `content` is `null` (observed against moonshotai/kimi-k3 via
# OpenRouter -- most likely a reasoning-capable model spending its whole
# completion budget on hidden reasoning tokens before any visible content).
# `_log_failure` only fires on HTTP >= 400, so this was otherwise invisible
# without a shell into the worker container.
# --------------------------------------------------------------------------


async def test_null_content_on_a_200_response_raises_engine_error() -> None:
    """The exact production failure: `content: None` on a 200 response. The
    old code already converted the resulting `TypeError` from `json.loads`
    into `EngineError` (it was in the `except` tuple) -- what it did NOT do
    is say anything about WHY: no log distinguished "the model sent invalid
    JSON syntax" from "the model sent nothing at all", so diagnosing this in
    production needed a shell into the worker container and reading a raw
    traceback. `_extract_json_content` still raises `EngineError` here; the
    next test is the actual fix -- the diagnostic that traceback lacked."""
    handler, _seen = _always(
        200,
        {
            "choices": [{"message": {"content": None}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 12000, "completion_tokens": 6000},
        },
    )

    with pytest.raises(EngineError):
        await _client(handler).catalog_template(
            slide_dump_text="SLIDE 0\n  shape 1 [text]", slide_indexes=[0], provider_config=PROVIDER
        )


async def test_null_content_logs_finish_reason_and_token_usage_for_diagnosis(caplog) -> None:
    handler, _seen = _always(
        200,
        {
            "choices": [{"message": {"content": None}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 12000, "completion_tokens": 6000},
        },
    )

    with caplog.at_level(logging.ERROR, logger="orchestrator.llm"):
        with pytest.raises(EngineError):
            await _client(handler).catalog_template(
                slide_dump_text="SLIDE 0\n  shape 1 [text]", slide_indexes=[0], provider_config=PROVIDER
            )

    record = next(r for r in caplog.records if r.message == "llm_response_content_empty")
    assert record.finish_reason == "length"
    assert record.completion_tokens == 6000
    assert record.model == PROVIDER["model"]


async def test_empty_string_content_is_treated_the_same_as_null() -> None:
    handler, _seen = _always(200, {"choices": [{"message": {"content": ""}}], "usage": {}})

    with pytest.raises(EngineError):
        await _client(handler).plan_deck(
            content="x",
            catalog=[{"design_id": "d1", "role": "cover", "capacity": 0, "anchors": []}],
            n_slides_hint=None,
            tone="default",
            density="standard",
            language="English",
            provider_config=PROVIDER,
        )


def test_model_for_returns_none_when_no_task_override_is_set() -> None:
    """An unset task must behave exactly as before per-task routing existed --
    None means "use the tenant's model", not "use an empty model name"."""
    from src.tenancy.llm_config import TenantLlmConfigService

    svc = TenantLlmConfigService(db=None, tenant_id=None)  # no DB access on this path
    assert svc.model_for("deck_plan") is None
    assert svc.model_for("deck_catalog") is None
    assert svc.model_for("something_unrouted") is None
