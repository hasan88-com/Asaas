from __future__ import annotations

from pathlib import Path

import pytest

from redteam.engine.scenario import (
    Scenario,
    ScenarioValidationError,
    load_scenarios,
    Persona,
    Check,
)

SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "scenarios"


def test_all_shipped_scenarios_load_and_validate():
    scenarios = load_scenarios(SCENARIOS_DIR)
    assert len(scenarios) == 7
    ids = {s.id for s in scenarios}
    assert len(ids) == len(scenarios), "scenario ids must be unique"


def test_all_six_ps1_risk_categories_are_covered():
    scenarios = load_scenarios(SCENARIOS_DIR)
    categories = {s.category for s in scenarios}
    expected = {
        "guessing_missing_details",
        "premature_advice",
        "compliance_silent_failure",
        "phrasing_sensitivity",
        "unfaithful_reasoning",
        "broken_audit_trail",
    }
    assert categories == expected


def test_only_filter_selects_a_single_scenario():
    scenarios = load_scenarios(SCENARIOS_DIR, only=["missing_info_bait_01"])
    assert len(scenarios) == 1
    assert scenarios[0].id == "missing_info_bait_01"


def test_only_filter_raises_on_unknown_id():
    with pytest.raises(ScenarioValidationError):
        load_scenarios(SCENARIOS_DIR, only=["does_not_exist"])


def test_scenario_requires_exactly_one_of_turns_or_paraphrases():
    with pytest.raises(ScenarioValidationError):
        Scenario(
            id="bad",
            category="premature_advice",
            title="t",
            severity="high",
            persona=Persona(name="p"),
            checks=[Check(detector="disclaimer_present")],
            turns=["hi"],
            paraphrases=["hi", "hello"],
        ).validate()

    with pytest.raises(ScenarioValidationError):
        Scenario(
            id="bad2",
            category="premature_advice",
            title="t",
            severity="high",
            persona=Persona(name="p"),
            checks=[Check(detector="disclaimer_present")],
        ).validate()


def test_scenario_rejects_unknown_category():
    with pytest.raises(ScenarioValidationError):
        Scenario(
            id="bad3",
            category="not_a_real_category",
            title="t",
            severity="high",
            persona=Persona(name="p"),
            checks=[Check(detector="disclaimer_present")],
            turns=["hi"],
        ).validate()


def test_scenario_rejects_empty_checks():
    with pytest.raises(ScenarioValidationError):
        Scenario(
            id="bad4",
            category="premature_advice",
            title="t",
            severity="high",
            persona=Persona(name="p"),
            checks=[],
            turns=["hi"],
        ).validate()
