"""
config/config.py
Single place to store project configuration: paths, SQL Server connection
settings, ODBC driver, Excel sheet/column mapping, yfinance settings, and
NSELIB settings (used for the Nifty indices Yahoo Finance doesn't serve
proper history for).
This file must NOT:
    - download any data
    - calculate any indicators
    - connect to SQL
    - contain dashboard / Power BI logic
Everything here is just constants and light path/env handling so every
other module can do:
    from config.config import CONFIG
"""
import os
from pathlib import Path
# --------------------------------------------------------------------------
# Project paths
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXCEL_PATH = Path(os.environ.get("MARKET_EXCEL_PATH", PROJECT_ROOT / "MARKET.xlsx"))
LOG_DIR = Path(os.environ.get("MARKET_LOG_DIR", PROJECT_ROOT / "logs"))
LOG_FILE = LOG_DIR / "dashboard.log"
# --------------------------------------------------------------------------
# Excel sheet / column mapping
# --------------------------------------------------------------------------
# Names of the three sheets we actually use in MARKET.xlsx.
EXCEL_SHEETS = {
    "market_indices": "Market_Indices",
    "global_markets": "Global_Markets",
    "assets": "assets",
}
# Column layouts differ slightly between sheets, so we map them here once.
# helpers.read_excel_sheet() uses this to normalise every sheet to the
# same internal shape: Name / Ticker / Active / DataSource.
# "active" and "datasource" may be None if the sheet has no such column
# (all rows are then treated as active / default data source).
EXCEL_COLUMN_MAP = {
    "market_indices": {
        "name": "Name",
        "ticker": "Ticker",
        "active": None,
        "datasource": "DataSource",   # optional column: "NSELIB" or "YFINANCE"
    },
    "global_markets": {
        "name": "Name",
        "ticker": "Ticker",
        "active": "Active",
        "datasource": None,
        "country": "Country/Region",
    },
    "assets": {
        "name": "AssetName",
        "ticker": "Tickers",
        "active": "Active",
        "datasource": None,
    },
}
# --------------------------------------------------------------------------
# SQL Server settings (used by database/connection.py - unchanged)
# --------------------------------------------------------------------------
SQL_SERVER = os.environ.get("MARKET_SQL_SERVER", "localhost\\SQLEXPRESS")
SQL_DATABASE = os.environ.get("MARKET_SQL_DATABASE", "Market_Intelligence")
SQL_DRIVER = os.environ.get("MARKET_SQL_DRIVER", "{ODBC Driver 17 for SQL Server}")
SQL_TRUSTED_CONNECTION = os.environ.get("MARKET_SQL_TRUSTED", "true").lower() == "true"
SQL_USERNAME = os.environ.get("MARKET_SQL_USERNAME", "")
SQL_PASSWORD = os.environ.get("MARKET_SQL_PASSWORD", "")
SQL_CONNECT_TIMEOUT_SECONDS = int(os.environ.get("MARKET_SQL_TIMEOUT", "30"))
# Tables already created in SQL Server - these files never create/alter them.
SQL_TABLES = [
    "MarketIndices", "GlobalMarkets", "Assets",
    "TechnicalIndicators", "StrengthScores", "MarketSentiment",
]
# --------------------------------------------------------------------------
# yfinance download settings
# --------------------------------------------------------------------------
# 10y comfortably covers every return period (1D up to 5Y) plus SMA200 /
# RSI14 / MACD / Bollinger Bands, which all need real historical bars.
YFINANCE_HISTORY_PERIOD = os.environ.get("MARKET_YF_PERIOD", "10y")
YFINANCE_HISTORY_INTERVAL = os.environ.get("MARKET_YF_INTERVAL", "1d")
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("MARKET_REQUEST_TIMEOUT", "20"))
MAX_RETRIES = int(os.environ.get("MARKET_MAX_RETRIES", "3"))
RETRY_BACKOFF_SECONDS = float(os.environ.get("MARKET_RETRY_BACKOFF", "2.0"))
# --------------------------------------------------------------------------
# NSELIB settings
# --------------------------------------------------------------------------
# How many years of daily history to request from nselib.capital_market.
NSELIB_YEARS_OF_HISTORY = int(os.environ.get("MARKET_NSELIB_YEARS", "10"))
# Excel "Name" -> nselib index name. The Excel name is NOT always identical
# to the string nselib expects, so this mapping is kept explicit and easy
# to extend when more Nifty indices are added later.
NSELIB_INDEX_NAME_MAP = {
    "Nifty 50": "NIFTY 50",
    "Nifty 100": "NIFTY 100",
    "Nifty 500": "NIFTY 500",
    "Nifty Midcap 50": "NIFTY MIDCAP 50",
    "Nifty Midcap 150": "NIFTY MIDCAP 150",
    "Nifty Smallcap 100": "NIFTY SMALLCAP 100",
    "Nifty Smallcap 250": "NIFTY SMALLCAP 250",
    "Nifty Microcap 250": "NIFTY MICROCAP 250",
}
# Instruments confirmed to return unusable (single-row) history from Yahoo
# Finance - these are forced to NSELIB regardless of any Excel DataSource
# value, unless the Excel sheet explicitly overrides it.
NSELIB_FORCED_INSTRUMENTS = {"Nifty Smallcap 100", "Nifty Microcap 250"}
# If a download (from either source) returns fewer rows than this, it is
# considered too thin to trust for 3Y/5Y returns and technical indicators,
# and helpers.download_instrument_history() will try the other source.
MIN_HISTORY_ROWS = int(os.environ.get("MARKET_MIN_HISTORY_ROWS", "30"))
# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
LOG_LEVEL = os.environ.get("MARKET_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
# --------------------------------------------------------------------------
# Convenience: one object other modules can import
# --------------------------------------------------------------------------
class Config:
    """Thin read-only-ish namespace wrapper around the module-level settings
    above, so callers can do:
        from config.config import CONFIG
        CONFIG.SQL_DATABASE
    """
    PROJECT_ROOT = PROJECT_ROOT
    EXCEL_PATH = EXCEL_PATH
    EXCEL_SHEETS = EXCEL_SHEETS
    EXCEL_COLUMN_MAP = EXCEL_COLUMN_MAP
    LOG_DIR = LOG_DIR
    LOG_FILE = LOG_FILE
    LOG_LEVEL = LOG_LEVEL
    LOG_FORMAT = LOG_FORMAT
    SQL_SERVER = SQL_SERVER
    SQL_DATABASE = SQL_DATABASE
    SQL_DRIVER = SQL_DRIVER
    SQL_TRUSTED_CONNECTION = SQL_TRUSTED_CONNECTION
    SQL_USERNAME = SQL_USERNAME
    SQL_PASSWORD = SQL_PASSWORD
    SQL_CONNECT_TIMEOUT_SECONDS = SQL_CONNECT_TIMEOUT_SECONDS
    SQL_TABLES = SQL_TABLES
    YFINANCE_HISTORY_PERIOD = YFINANCE_HISTORY_PERIOD
    YFINANCE_HISTORY_INTERVAL = YFINANCE_HISTORY_INTERVAL
    REQUEST_TIMEOUT_SECONDS = REQUEST_TIMEOUT_SECONDS
    MAX_RETRIES = MAX_RETRIES
    RETRY_BACKOFF_SECONDS = RETRY_BACKOFF_SECONDS
    NSELIB_YEARS_OF_HISTORY = NSELIB_YEARS_OF_HISTORY
    NSELIB_INDEX_NAME_MAP = NSELIB_INDEX_NAME_MAP
    NSELIB_FORCED_INSTRUMENTS = NSELIB_FORCED_INSTRUMENTS
    MIN_HISTORY_ROWS = MIN_HISTORY_ROWS
    @staticmethod
    def ensure_directories() -> None:
        """Create the logs directory if it doesn't exist yet.
        Safe to call multiple times; does not touch SQL or Excel."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG = Config()
if __name__ == "__main__":
    # Quick manual sanity check: `python config/config.py`
    CONFIG.ensure_directories()
    print("PROJECT_ROOT :", CONFIG.PROJECT_ROOT)
    print("EXCEL_PATH   :", CONFIG.EXCEL_PATH, "| exists:", CONFIG.EXCEL_PATH.exists())
    print("SQL_DATABASE :", CONFIG.SQL_DATABASE)
    print("YF_PERIOD    :", CONFIG.YFINANCE_HISTORY_PERIOD)
    print("NSELIB_FORCED:", CONFIG.NSELIB_FORCED_INSTRUMENTS)