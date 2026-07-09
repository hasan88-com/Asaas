"""
Shared result/transcript data model.

Adapters produce a RunResult; detectors read it and produce DetectorOutcomes;
the scorer aggregates outcomes across a run of scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class RunResult:
    """Everything a detector might need to judge one scenario execution."""

    scenario_id: str
    transcript: list[Turn] = field(default_factory=list)

    # For paraphrase-set scenarios: one final assistant response per paraphrase,
    # in the same order the paraphrases were sent. Empty for single-turn scenarios.
    paraphrase_responses: list[str] = field(default_factory=list)

    # Optional structured side-channel state an adapter can supply for deeper
    # checks the transcript text alone can't answer (e.g. did a DB row actually
    # change). Generic HTTP targets leave these as {}; the Asaas direct adapter
    # populates them from the database.
    state_before: dict = field(default_factory=dict)
    state_after: dict = field(default_factory=dict)

    # Populated if the adapter itself errored (network failure, exception) —
    # detectors should treat this as a hard fail for the scenario, not silently skip.
    adapter_error: str | None = None

    @property
    def final_response(self) -> str:
        for turn in reversed(self.transcript):
            if turn.role == "assistant":
                return turn.content
        return ""

    @property
    def full_text(self) -> str:
        return "\n".join(t.content for t in self.transcript if t.role == "assistant")


@dataclass
class DetectorOutcome:
    detector: str
    passed: bool
    severity: str  # "critical" | "high" | "medium" | "low"
    message: str
    evidence: str = ""
