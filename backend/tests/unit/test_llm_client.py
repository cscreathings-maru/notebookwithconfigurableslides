"""T-2.3: the LLM must be as resilient and as diagnosable as the other engines.

`LlmClient` called httpx directly -- no retry, no backoff, no circuit breaker, unlike
`OpenNotebookClient` and `PresentonClient`. Every failure collapsed into the single
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
    # Arrange
    handler, _seen = _always(401, text="key sk-or-secret-123 is revoked")

    # Act
    with pytest.raises(EngineError) as excinfo:
        await _client(handler).chat(system="s", user="u", provider_config=PROVIDER)

    # Assert
    assert "sk-or-secret-123" not in str(excinfo.value)
    assert str(excinfo.value) == "LLM provider request failed."


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
