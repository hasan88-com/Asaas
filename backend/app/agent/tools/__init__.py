"""Agent tool registry — async functions that read/write via services, never raw DDL.

Reachability:
  * CHAT-REACHABLE — imported and invoked by an agent role during a chat turn.
  * REST-ONLY      — exposed via a REST endpoint (or background monitor), NOT
                     wired into any role. Kept here so the test suite can import
                     them centrally, but deliberately unreachable from chat to
                     honour RULES.md A1.1 (no portfolio/state change without an
                     explicit user action) and A1.2 (abstraction discipline).
"""

# --- CHAT-REACHABLE (wired into roles) -------------------------------------
from app.agent.tools.analyze_profile import analyze_profile              # profiler
from app.agent.tools.suggest_portfolio import suggest_portfolio          # optimizer (first draft)
from app.agent.tools.reoptimize import reoptimize                        # optimizer (existing portfolio)
from app.agent.tools.check_diversification import check_diversification    # optimizer
from app.agent.tools.track_value import track_value                      # optimizer (track intent)
from app.agent.tools.fetch_relevant_news import fetch_relevant_news      # news_materiality
from app.agent.tools.assess_materiality import assess_materiality        # news_materiality
from app.agent.tools.analyze_rate_impact import analyze_rate_impact      # rate_impact
from app.agent.tools.extract_company_info import extract_company_info    # valuation
from app.agent.tools.run_dcf import run_dcf                              # valuation
from app.agent.tools.run_monte_carlo import run_monte_carlo              # valuation
from app.agent.tools.run_multiples import run_multiples                  # valuation
from app.agent.tools.run_technical_analysis import run_technical_analysis  # technical

# --- REST-ONLY (NOT wired into any role) -----------------------------------
from app.agent.tools.confirm_holdings import confirm_holdings            # POST /portfolio/confirm
from app.agent.tools.flag_event import flag_event                        # background monitors only

__all__ = [
    "analyze_profile",
    "suggest_portfolio",
    "reoptimize",
    "check_diversification",
    "track_value",
    "fetch_relevant_news",
    "assess_materiality",
    "analyze_rate_impact",
    "extract_company_info",
    "run_dcf",
    "run_monte_carlo",
    "run_multiples",
    "run_technical_analysis",
    "confirm_holdings",
    "flag_event",
]
