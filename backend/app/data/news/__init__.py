"""News scraper sub-package — PSX, Dawn, Financial Daily, Profit, Tribune, APP."""

from app.data.news.psx_scraper import PSXScraper
from app.data.news.sbp_scraper import SBPScraper
from app.data.news.business_recorder import BusinessRecorderScraper
from app.data.news.dawn_scraper import DawnScraper
from app.data.news.financial_daily import FinancialDailyScraper
from app.data.news.profit_scraper import ProfitScraper
from app.data.news.tribune_scraper import TribuneScraper
from app.data.news.app_scraper import APPScraper
from app.data.news.ary_scraper import ARYNewsScraper
from app.data.news.normalizer import normalize

__all__ = [
    "PSXScraper",
    "SBPScraper",
    "BusinessRecorderScraper",
    "DawnScraper",
    "FinancialDailyScraper",
    "ProfitScraper",
    "TribuneScraper",
    "APPScraper",
    "ARYNewsScraper",
    "normalize",
]
