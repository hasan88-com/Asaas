"""
Red-Teaming Engine CLI.

    # Against a live Asaas deployment's HTTP API (or any advice API speaking
    # the same content-delta SSE / plain-JSON chat protocol):
    python -m redteam.cli --target http --base-url http://localhost:8000/api/v1 \\
        --auth-header "Bearer <jwt>" --out redteam/reports/report.html

    # Direct-to-orchestrator (needs backend/ on PYTHONPATH and a reachable DB —
    # set DATABASE_URL or TEST_DATABASE_URL as backend/tests/conftest.py does):
    python -m redteam.cli --target direct --out redteam/reports/report.html

Only scenarios matching --scenarios (comma-separated ids, default: all) run.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from redteam.engine import report as report_mod
from redteam.engine.runner import run_scenario
from redteam.engine.scenario import load_scenarios
from redteam.engine.scorer import score

DEFAULT_SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Red-team an agentic advice API (PS1).")
    parser.add_argument("--target", choices=["direct", "http"], default="direct")
    parser.add_argument(
        "--scenarios", default="all", help="Comma-separated scenario ids, or 'all' (default)."
    )
    parser.add_argument("--scenarios-dir", default=str(DEFAULT_SCENARIOS_DIR))
    parser.add_argument("--out", default=str(Path(__file__).parent / "reports" / "report"))
    parser.add_argument(
        "--format", choices=["html", "md", "json", "all"], default="all",
        help="Report format(s) to write; 'all' writes .html/.md/.json alongside --out's stem.",
    )
    # http target options
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--chat-path", default="/chat")
    parser.add_argument("--auth-header", default=os.environ.get("REDTEAM_AUTH_HEADER"))
    parser.add_argument("--response-mode", choices=["sse", "json"], default="sse")
    return parser


async def _build_target(args: argparse.Namespace):
    if args.target == "http":
        from redteam.engine.targets.http_adapter import HTTPChatAdapter, HTTPTargetConfig

        config = HTTPTargetConfig(
            base_url=args.base_url,
            chat_path=args.chat_path,
            auth_header=args.auth_header,
            response_mode=args.response_mode,
        )
        return HTTPChatAdapter(config), None

    # direct: needs a live AsyncSession against the backend's DB.
    db_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print(
            "ERROR: --target direct requires TEST_DATABASE_URL or DATABASE_URL to be set.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from redteam.engine.targets.asaas_direct import AsaasDirectAdapter

    engine = create_async_engine(db_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session_cm = factory()
    session = await session_cm.__aenter__()
    adapter = AsaasDirectAdapter(session)
    return adapter, (session_cm, engine)


async def _teardown_direct(cleanup) -> None:
    if cleanup is None:
        return
    session_cm, engine = cleanup
    await session_cm.__aexit__(None, None, None)
    await engine.dispose()


async def main_async(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    only = None if args.scenarios == "all" else [s.strip() for s in args.scenarios.split(",")]
    scenarios = load_scenarios(Path(args.scenarios_dir), only=only)
    if not scenarios:
        print("No scenarios matched.", file=sys.stderr)
        return 1

    target, cleanup = await _build_target(args)
    try:
        pairs = []
        for scenario in scenarios:
            print(f"Running {scenario.id} ({scenario.category})...", file=sys.stderr)
            result = await run_scenario(scenario, target)
            pairs.append((scenario, result))
    finally:
        await _teardown_direct(cleanup)

    report = score(pairs)

    out_stem = Path(args.out)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    formats = ["html", "md", "json"] if args.format == "all" else [args.format]
    for fmt in formats:
        path = out_stem.with_suffix(f".{fmt}")
        if fmt == "html":
            path.write_text(report_mod.render_html(report))
        elif fmt == "md":
            path.write_text(report_mod.render_markdown(report))
        else:
            path.write_text(report_mod.render_json(report))
        print(f"Wrote {path}", file=sys.stderr)

    print(f"\n{report.passed_scenarios}/{report.total_scenarios} scenarios passed "
          f"({report.pass_rate:.0%})")
    return 0 if report.pass_rate == 1.0 else 1


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
