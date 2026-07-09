"""
Executes one Scenario against one TargetAdapter, producing a RunResult.

Turn-script scenarios run as a single session (history matters — e.g. an
onboarding sequence). Paraphrase-set scenarios run each paraphrase in its own
fresh session — the point is to isolate N independently-worded but
semantically-identical requests, so any divergence in response is a
phrasing-sensitivity signal, not conversation-history noise.
"""

from __future__ import annotations

import logging

from redteam.engine.results import RunResult, Turn
from redteam.engine.scenario import Scenario
from redteam.engine.targets.base import TargetAdapter

logger = logging.getLogger("redteam.runner")


async def run_scenario(scenario: Scenario, target: TargetAdapter) -> RunResult:
    result = RunResult(scenario_id=scenario.id)
    try:
        if scenario.is_paraphrase_set:
            await _run_paraphrase_set(scenario, target, result)
        else:
            await _run_turn_script(scenario, target, result)
    except Exception as exc:  # noqa: BLE001 - a target failure IS the finding
        logger.error("Scenario %s errored against target: %s", scenario.id, exc)
        result.adapter_error = str(exc)
    return result


async def _run_turn_script(scenario: Scenario, target: TargetAdapter, result: RunResult) -> None:
    session_id = await target.new_session(scenario.persona.name, scenario.setup)
    result.state_before = await target.get_state(session_id)
    for message in scenario.turns:
        result.transcript.append(Turn(role="user", content=message))
        response = await target.send(session_id, message)
        result.transcript.append(Turn(role="assistant", content=response))
    result.state_after = await target.get_state(session_id)


async def _run_paraphrase_set(scenario: Scenario, target: TargetAdapter, result: RunResult) -> None:
    for message in scenario.paraphrases:
        session_id = await target.new_session(scenario.persona.name, scenario.setup)
        result.transcript.append(Turn(role="user", content=message))
        response = await target.send(session_id, message)
        result.transcript.append(Turn(role="assistant", content=response))
        result.paraphrase_responses.append(response)
