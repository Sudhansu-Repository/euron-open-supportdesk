"""AC2 against a real local model: ``make up`` with the ollama profile, ``make ollama-pull``,
then ``make test-ollama``. Skipped when no Ollama with the model answers at OLLAMA_URL.

The model is small and runs on the CPU, so this checks that the zero-API-key path works
end to end (answer grounded in the knowledge, with a citation, no cloud call), not its
eloquence.
"""

from __future__ import annotations

import os

import httpx
import pytest

from supportdesk.ai.providers.base import ChatMessage
from supportdesk.ai.providers.ollama import OllamaChat

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:4834")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
pytestmark = pytest.mark.ollama


def _available() -> bool:
    try:
        tags = httpx.get(f"{OLLAMA}/api/tags", timeout=3).json()
    except (httpx.HTTPError, ValueError):
        return False
    return any(m.get("name", "").startswith(MODEL) for m in tags.get("models", []))


@pytest.fixture(scope="module", autouse=True)
def _need_ollama() -> None:
    if not _available():
        pytest.skip(
            f"no Ollama with {MODEL} at {OLLAMA} (make up with the ollama profile, then make ollama-pull)"
        )


async def test_the_local_model_answers_from_the_sources() -> None:
    from supportdesk.ai.answer import validate
    from supportdesk.ai.prompts import answer_messages
    from tests.unit.ai.test_text_and_redaction import hit

    passage = hit(
        "Q: How long does shipping take?\nA: Standard shipping takes 3 to 5 business days.",
        title="FAQ",
        heading="How long does shipping take?",
    )
    async with httpx.AsyncClient() as client:
        chat = OllamaChat(client, OLLAMA, timeout_s=180, allow_private=True)
        completion = await chat.complete(
            answer_messages("Lumen", [passage], [], "How long does shipping take?", "en"),
            model=MODEL,
            max_tokens=120,
        )
    answer = validate(completion.text, [passage], 0.5)
    assert answer.grounded, completion.text
    assert "3" in answer.text and "5" in answer.text
    assert completion.input_tokens > 0 and completion.output_tokens > 0


async def test_the_local_model_says_no_answer_when_the_sources_do_not_cover_it() -> None:
    from supportdesk.ai.answer import validate
    from supportdesk.ai.prompts import answer_messages
    from tests.unit.ai.test_text_and_redaction import hit

    passage = hit(
        "Q: How long does shipping take?\nA: Standard shipping takes 3 to 5 business days."
    )
    async with httpx.AsyncClient() as client:
        chat = OllamaChat(client, OLLAMA, timeout_s=180, allow_private=True)
        completion = await chat.complete(
            answer_messages("Lumen", [passage], [], "Do you support SAML single sign-on?", "en"),
            model=MODEL,
            max_tokens=60,
        )
    # Either the model says NO_ANSWER, or whatever it wrote cannot be traced to the source:
    # in both cases the customer gets a handoff, never an invented answer.
    assert not validate(completion.text, [passage], 0.5).grounded, completion.text


async def test_triage_in_json_mode() -> None:
    async with httpx.AsyncClient() as client:
        chat = OllamaChat(client, OLLAMA, timeout_s=180, allow_private=True)
        completion = await chat.complete(
            [
                ChatMessage("system", "Reply with a JSON object with a key category."),
                ChatMessage("user", "My invoice is wrong"),
            ],
            model=MODEL,
            max_tokens=40,
            json_mode=True,
        )
    assert completion.text.strip().startswith("{")
