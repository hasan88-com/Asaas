from __future__ import annotations

import json

from redteam.engine import report as report_mod
from redteam.engine.results import RunResult, Turn
from redteam.engine.scenario import Check, Persona, Scenario
from redteam.engine.scorer import score


def _passing_scenario_and_result():
    scenario = Scenario(
        id="pass_case",
        category="compliance_silent_failure",
        title="Should pass",
        severity="high",
        persona=Persona(name="p"),
        checks=[Check(detector="disclaimer_present")],
        turns=["hi"],
    )
    result = RunResult(scenario_id=scenario.id)
    result.transcript = [
        Turn(role="user", content="hi"),
        Turn(role="assistant", content="Here's a suggestion, not financial advice."),
    ]
    return scenario, result


def _failing_scenario_and_result():
    scenario = Scenario(
        id="fail_case",
        category="compliance_silent_failure",
        title="Should fail",
        severity="critical",
        persona=Persona(name="p"),
        checks=[Check(detector="denylist_certainty_language")],
        turns=["hi"],
    )
    result = RunResult(scenario_id=scenario.id)
    result.transcript = [
        Turn(role="user", content="hi"),
        Turn(role="assistant", content="This is guaranteed, risk-free money."),
    ]
    return scenario, result


def test_score_aggregates_pass_and_fail_counts():
    report = score([_passing_scenario_and_result(), _failing_scenario_and_result()])
    assert report.total_scenarios == 2
    assert report.passed_scenarios == 1
    assert report.pass_rate == 0.5
    assert len(report.failed_scenarios) == 1
    assert report.failed_scenarios[0].scenario.id == "fail_case"


def test_category_pass_rate_groups_by_category():
    report = score([_passing_scenario_and_result(), _failing_scenario_and_result()])
    rates = report.category_pass_rate()
    assert rates["compliance_silent_failure"] == (1, 2)


def test_render_json_round_trips_key_fields():
    report = score([_passing_scenario_and_result(), _failing_scenario_and_result()])
    data = json.loads(report_mod.render_json(report))
    assert data["total_scenarios"] == 2
    assert data["passed_scenarios"] == 1
    ids = {s["id"] for s in data["scenarios"]}
    assert ids == {"pass_case", "fail_case"}


def test_render_markdown_includes_failures_section():
    report = score([_passing_scenario_and_result(), _failing_scenario_and_result()])
    md = report_mod.render_markdown(report)
    assert "fail_case" in md
    assert "pass_case" not in md.split("## Findings")[1]  # only failures listed under Findings


def test_render_html_marks_fail_rows():
    report = score([_passing_scenario_and_result(), _failing_scenario_and_result()])
    html = report_mod.render_html(report)
    assert "class='fail'" in html
    assert "class='pass'" in html
    assert "fail_case" in html and "pass_case" in html
