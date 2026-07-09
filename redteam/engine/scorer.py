"""
Aggregates scenario results into a Report: per-scenario pass/fail, rolled up
by PS1 risk category and severity, plus the flat list of failed findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from redteam.engine.detectors import evaluate_checks
from redteam.engine.results import DetectorOutcome, RunResult
from redteam.engine.scenario import Scenario

_SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass
class ScenarioReport:
    scenario: Scenario
    result: RunResult
    outcomes: list[DetectorOutcome]

    @property
    def passed(self) -> bool:
        return all(o.passed for o in self.outcomes)

    @property
    def worst_failed_severity(self) -> str | None:
        failed = [o for o in self.outcomes if not o.passed]
        if not failed:
            return None
        return max(failed, key=lambda o: _SEVERITY_WEIGHT.get(o.severity, 0)).severity


@dataclass
class Report:
    scenario_reports: list[ScenarioReport] = field(default_factory=list)

    @property
    def total_scenarios(self) -> int:
        return len(self.scenario_reports)

    @property
    def passed_scenarios(self) -> int:
        return sum(1 for r in self.scenario_reports if r.passed)

    @property
    def failed_scenarios(self) -> list[ScenarioReport]:
        return [r for r in self.scenario_reports if not r.passed]

    def by_category(self) -> dict[str, list[ScenarioReport]]:
        out: dict[str, list[ScenarioReport]] = {}
        for r in self.scenario_reports:
            out.setdefault(r.scenario.category, []).append(r)
        return out

    def category_pass_rate(self) -> dict[str, tuple[int, int]]:
        """category -> (passed, total)"""
        rates: dict[str, tuple[int, int]] = {}
        for category, reports in self.by_category().items():
            passed = sum(1 for r in reports if r.passed)
            rates[category] = (passed, len(reports))
        return rates

    @property
    def pass_rate(self) -> float:
        if not self.total_scenarios:
            return 1.0
        return self.passed_scenarios / self.total_scenarios


def score(scenarios_and_results: list[tuple[Scenario, RunResult]]) -> Report:
    reports = [
        ScenarioReport(scenario=scenario, result=result, outcomes=evaluate_checks(scenario, result))
        for scenario, result in scenarios_and_results
    ]
    return Report(scenario_reports=reports)
