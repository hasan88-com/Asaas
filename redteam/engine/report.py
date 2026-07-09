"""
Renders a Report to Markdown, JSON, or a self-contained HTML page.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape

from redteam.engine.scorer import Report

CATEGORY_LABELS = {
    "guessing_missing_details": "Guessing missing client details",
    "premature_advice": "Premature advice",
    "compliance_silent_failure": "Silent compliance failure",
    "phrasing_sensitivity": "Unpredictable behavior from phrasing",
    "unfaithful_reasoning": "Made-up AI reasoning / hallucination",
    "broken_audit_trail": "Broken audit trail",
}


def render_json(report: Report) -> str:
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": report.total_scenarios,
        "passed_scenarios": report.passed_scenarios,
        "pass_rate": report.pass_rate,
        "category_pass_rate": {
            cat: {"passed": p, "total": t} for cat, (p, t) in report.category_pass_rate().items()
        },
        "scenarios": [
            {
                "id": r.scenario.id,
                "category": r.scenario.category,
                "title": r.scenario.title,
                "severity": r.scenario.severity,
                "passed": r.passed,
                "adapter_error": r.result.adapter_error,
                "outcomes": [
                    {
                        "detector": o.detector,
                        "passed": o.passed,
                        "severity": o.severity,
                        "message": o.message,
                        "evidence": o.evidence,
                    }
                    for o in r.outcomes
                ],
            }
            for r in report.scenario_reports
        ],
    }
    return json.dumps(data, indent=2, default=str)


def render_markdown(report: Report) -> str:
    lines = [
        "# Red-Team Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"**{report.passed_scenarios}/{report.total_scenarios} scenarios passed "
        f"({report.pass_rate:.0%})**",
        "",
        "## By PS1 risk category",
        "",
        "| Category | Passed | Total |",
        "|---|---|---|",
    ]
    for category, (passed, total) in sorted(report.category_pass_rate().items()):
        label = CATEGORY_LABELS.get(category, category)
        lines.append(f"| {label} | {passed} | {total} |")

    failures = report.failed_scenarios
    lines += ["", "## Findings", ""]
    if not failures:
        lines.append("No failing scenarios.")
    for r in failures:
        lines.append(f"### [{r.scenario.severity.upper()}] {r.scenario.id} — {r.scenario.title}")
        lines.append(f"_Category: {CATEGORY_LABELS.get(r.scenario.category, r.scenario.category)}_")
        lines.append("")
        for o in r.outcomes:
            if o.passed:
                continue
            lines.append(f"- **{o.detector}**: {o.message}")
            if o.evidence:
                lines.append(f"  - evidence: `{o.evidence[:200]}`")
        lines.append("")
    return "\n".join(lines)


def render_html(report: Report) -> str:
    rows = []
    for r in report.scenario_reports:
        status = "PASS" if r.passed else "FAIL"
        status_class = "pass" if r.passed else "fail"
        detail = "<br>".join(
            escape(f"{'✓' if o.passed else '✗'} {o.detector}: {o.message}")
            for o in r.outcomes
        )
        rows.append(
            f"<tr class='{status_class}'>"
            f"<td>{escape(r.scenario.id)}</td>"
            f"<td>{escape(CATEGORY_LABELS.get(r.scenario.category, r.scenario.category))}</td>"
            f"<td>{escape(r.scenario.severity)}</td>"
            f"<td class='status'>{status}</td>"
            f"<td>{detail}</td>"
            "</tr>"
        )

    cat_rows = "".join(
        f"<tr><td>{escape(CATEGORY_LABELS.get(cat, cat))}</td><td>{p}/{t}</td></tr>"
        for cat, (p, t) in sorted(report.category_pass_rate().items())
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Red-Team Report</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2rem; background:#F6F4ED; color:#16201C; }}
  h1 {{ font-size: 1.4rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; background:#FFFEFB; }}
  th, td {{ border: 1px solid #DCD8CC; padding: 8px 10px; text-align: left; font-size: 0.9rem; vertical-align: top; }}
  th {{ background: #E1F1EA; }}
  tr.fail td.status {{ color: #A8401F; font-weight: 600; }}
  tr.pass td.status {{ color: #0F6E56; font-weight: 600; }}
  .summary {{ font-size: 1.1rem; margin-bottom: 1rem; }}
</style></head>
<body>
<h1>Red-Team Report</h1>
<div class="summary">{report.passed_scenarios}/{report.total_scenarios} scenarios passed
({report.pass_rate:.0%})</div>
<h2>By PS1 risk category</h2>
<table><tr><th>Category</th><th>Passed / Total</th></tr>{cat_rows}</table>
<h2>Scenarios</h2>
<table>
<tr><th>ID</th><th>Category</th><th>Severity</th><th>Status</th><th>Detectors</th></tr>
{"".join(rows)}
</table>
</body></html>"""
