from __future__ import annotations

import pytest

from redteam.engine.runner import run_scenario
from redteam.engine.scenario import Check, Persona, Scenario


class _FakeTarget:
    """In-memory TargetAdapter for testing the runner without any real backend."""

    def __init__(self, canned_response: str = "ok", state: dict | None = None):
        self.canned_response = canned_response
        self.state = state or {}
        self.sent: list[tuple[str, str]] = []
        self.sessions_created = 0

    async def new_session(self, persona_name: str, setup: dict) -> str:
        self.sessions_created += 1
        return f"session-{self.sessions_created}"

    async def send(self, session_id: str, message: str) -> str:
        self.sent.append((session_id, message))
        return f"{self.canned_response}:{message}"

    async def get_state(self, session_id: str) -> dict:
        return dict(self.state)


def _turn_scenario(turns: list[str]) -> Scenario:
    return Scenario(
        id="s1",
        category="premature_advice",
        title="t",
        severity="high",
        persona=Persona(name="p"),
        checks=[Check(detector="disclaimer_present")],
        turns=turns,
    )


def _paraphrase_scenario(paraphrases: list[str]) -> Scenario:
    return Scenario(
        id="s2",
        category="phrasing_sensitivity",
        title="t",
        severity="medium",
        persona=Persona(name="p"),
        checks=[Check(detector="consistent_intent_across_paraphrases")],
        paraphrases=paraphrases,
    )


@pytest.mark.asyncio
async def test_run_scenario_turn_script_builds_transcript_in_order():
    target = _FakeTarget(canned_response="reply")
    scenario = _turn_scenario(["first", "second"])
    result = await run_scenario(scenario, target)

    assert [t.content for t in result.transcript] == [
        "first",
        "reply:first",
        "second",
        "reply:second",
    ]
    assert target.sessions_created == 1, "turn-script scenarios use a single session"


@pytest.mark.asyncio
async def test_run_scenario_paraphrase_set_uses_fresh_session_per_paraphrase():
    target = _FakeTarget(canned_response="reply")
    scenario = _paraphrase_scenario(["a", "b", "c"])
    result = await run_scenario(scenario, target)

    assert target.sessions_created == 3
    assert result.paraphrase_responses == ["reply:a", "reply:b", "reply:c"]


@pytest.mark.asyncio
async def test_run_scenario_captures_state_before_and_after():
    target = _FakeTarget(state={"confirmed_count": 1})
    scenario = _turn_scenario(["hi"])
    result = await run_scenario(scenario, target)

    assert result.state_before == {"confirmed_count": 1}
    assert result.state_after == {"confirmed_count": 1}


@pytest.mark.asyncio
async def test_run_scenario_records_adapter_error_instead_of_raising():
    class _BrokenTarget:
        async def new_session(self, persona_name, setup):
            raise RuntimeError("target unreachable")

        async def send(self, session_id, message):
            return ""

        async def get_state(self, session_id):
            return {}

    scenario = _turn_scenario(["hi"])
    result = await run_scenario(scenario, _BrokenTarget())
    assert result.adapter_error is not None
    assert "unreachable" in result.adapter_error
