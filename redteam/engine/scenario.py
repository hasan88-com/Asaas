"""
Scenario definition + YAML loader.

A scenario is either:
  - a scripted multi-turn conversation ("turns"), or
  - a paraphrase set ("paraphrases") — the same underlying request phrased N
    different ways, used to probe prompt-sensitivity (PS1 risk: "Unpredictable
    behavior triggered by minor changes in user phrasing").

Exactly one of the two must be present. Each scenario carries one or more
checks — detector name + optional args — evaluated against the resulting
RunResult by the scorer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

VALID_CATEGORIES = frozenset(
    {
        "guessing_missing_details",
        "premature_advice",
        "compliance_silent_failure",
        "phrasing_sensitivity",
        "unfaithful_reasoning",
        "broken_audit_trail",
    }
)
VALID_SEVERITIES = frozenset({"critical", "high", "medium", "low"})


class ScenarioValidationError(ValueError):
    pass


@dataclass
class Persona:
    name: str
    description: str = ""


@dataclass
class Check:
    detector: str
    args: dict = field(default_factory=dict)


@dataclass
class Scenario:
    id: str
    category: str
    title: str
    severity: str
    persona: Persona
    checks: list[Check]
    turns: list[str] = field(default_factory=list)
    paraphrases: list[str] = field(default_factory=list)
    setup: dict = field(default_factory=dict)  # adapter-specific fixture hints

    @property
    def is_paraphrase_set(self) -> bool:
        return bool(self.paraphrases)

    def validate(self) -> None:
        if self.category not in VALID_CATEGORIES:
            raise ScenarioValidationError(
                f"{self.id}: unknown category '{self.category}' "
                f"(must be one of {sorted(VALID_CATEGORIES)})"
            )
        if self.severity not in VALID_SEVERITIES:
            raise ScenarioValidationError(
                f"{self.id}: unknown severity '{self.severity}' "
                f"(must be one of {sorted(VALID_SEVERITIES)})"
            )
        if bool(self.turns) == bool(self.paraphrases):
            raise ScenarioValidationError(
                f"{self.id}: exactly one of 'turns' or 'paraphrases' must be set"
            )
        if not self.checks:
            raise ScenarioValidationError(f"{self.id}: scenario has no checks")


def _parse_scenario(raw: dict[str, Any], source: Path) -> Scenario:
    try:
        persona_raw = raw["persona"]
        scenario = Scenario(
            id=raw["id"],
            category=raw["category"],
            title=raw["title"],
            severity=raw["severity"],
            persona=Persona(
                name=persona_raw["name"], description=persona_raw.get("description", "")
            ),
            checks=[
                Check(detector=c["detector"], args=c.get("args", {}) or {})
                for c in raw["checks"]
            ],
            turns=list(raw.get("turns", []) or []),
            paraphrases=list(raw.get("paraphrases", []) or []),
            setup=raw.get("setup", {}) or {},
        )
    except KeyError as exc:
        raise ScenarioValidationError(f"{source}: missing required field {exc}") from exc
    scenario.validate()
    return scenario


def load_scenario_file(path: Path) -> Scenario:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ScenarioValidationError(f"{path}: scenario file must contain a YAML mapping")
    return _parse_scenario(raw, path)


def load_scenarios(directory: Path, only: list[str] | None = None) -> list[Scenario]:
    """Load and validate every *.yaml scenario in `directory`, sorted by id.

    `only`, if given, filters to scenario ids (exact match) — used by the CLI's
    ``--scenarios`` flag.
    """
    scenarios: list[Scenario] = []
    for path in sorted(directory.glob("*.yaml")):
        scenario = load_scenario_file(path)
        if only and scenario.id not in only:
            continue
        scenarios.append(scenario)
    if only:
        found = {s.id for s in scenarios}
        missing = set(only) - found
        if missing:
            raise ScenarioValidationError(f"Requested scenario id(s) not found: {sorted(missing)}")
    return scenarios
