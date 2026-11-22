"""
utils/helpers.py
Generic reusable utility functions for the STOCK_MARKET_DASHBOARD project.
This file provides:
    - Logging
    - Excel worksheet reading
    - Column validation
    - Ticker cleaning
    - Date conversion
    - Numeric conversion
    - Percentage calculations
    - Historical price lookup
    - Return-period calculations
    - YFinance historical-data downloading
    - Retry utilities
Data-source architecture:
    - Market indices -> handled directly by downloaders/market_indices.py
      using jugaad_data.
    - Global markets -> yfinance
    - Assets -> yfinance
This file must NOT:
    - perform SQL operations
    - contain Jugaad/NSELIB index-download logic
    - calculate technical indicators
    - calculate strength scores
    - calculate market sentiment
    - contain Power BI logic
    - contain application/GUI logic
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, date, timedelta
from typing import Callable, Iterable, Optional, TypeVar
import numpy as np
import pandas as pd
import yfinance as yf
from config.config import CONFIG
T = TypeVar("T")
# ==========================================================================
# LOGGING
# ==========================================================================
def setup_logging(name: str = "market_dashboard") -> logging.Logger:
    """
    Configure and return the project logger.
    The logger writes to:
        1. logs/dashboard.log
        2. Console
    Calling this function multiple times will not create duplicate handlers.
    """
    CONFIG.ensure_directories()
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(CONFIG.LOG_LEVEL)
    formatter = logging.Formatter(CONFIG.LOG_FORMAT)
    file_handler = logging.FileHandler(
        CONFIG.LOG_FILE,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
logger = setup_logging()
# ==========================================================================
# EXCEL FUNCTIONS
# ==========================================================================
def validate_columns(
    df: pd.DataFrame,
    required: Iterable[str],
    context: str = ""
) -> bool:
    """
    Validate that all required columns exist in a DataFrame.
    Raises:
        ValueError: if one or more required columns are missing.
    """
    required = list(required)
    missing = [column for column in required if column not in df.columns]
    if missing:
        message = (
            f"Missing required column(s) {missing}"
            f"{' in ' + context if context else ''}."
        )
        raise ValueError(message)
    return True
def clean_ticker(ticker) -> Optional[str]:
    """
    Clean a ticker/symbol value read from Excel.
    Examples:
        ' RELIANCE.NS ' -> 'RELIANCE.NS'
        '^NSEI' -> '^NSEI'
        NaN -> None
    """
    if ticker is None:
        return None
    if pd.isna(ticker):
        return None
    value = str(ticker).strip()
    if not value:
        return None
    return value
def read_excel_sheet(sheet_key: str) -> pd.DataFrame:
    """
    Read one of the project's master Excel worksheets.
    Supported sheet keys are normally:
        - market_indices
        - global_markets
        - assets
        - stocks
        - sectors / sector_indices if configured
    The exact worksheet name and column mapping are obtained from CONFIG.
    Returns a normalized DataFrame containing:
        Name
        Ticker
        Active
        DataSource
    """
    if sheet_key not in CONFIG.EXCEL_SHEETS:
        raise ValueError(
            f"Unknown sheet_key '{sheet_key}'. "
            f"Expected one of: {list(CONFIG.EXCEL_SHEETS)}"
        )
    if not CONFIG.EXCEL_PATH.exists():
        raise FileNotFoundError(
            f"MARKET.xlsx not found at {CONFIG.EXCEL_PATH}"
        )
    sheet_name = CONFIG.EXCEL_SHEETS[sheet_key]
    column_map = CONFIG.EXCEL_COLUMN_MAP[sheet_key]
    df = pd.read_excel(
        CONFIG.EXCEL_PATH,
        sheet_name=sheet_name
    )
    validate_columns(
        df,
        required=[
            column_map["name"],
            column_map["ticker"]
        ],
        context=f"sheet '{sheet_name}'"
    )
    out = pd.DataFrame()
    out["Name"] = df[column_map["name"]]
    out["Ticker"] = df[column_map["ticker"]].map(clean_ticker)
    active_col = column_map.get("active")
    if active_col and active_col in df.columns:
        out["Active"] = (
            df[active_col]
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("yes")
        )
    else:
        out["Active"] = True
    datasource_col = column_map.get("datasource")
    if datasource_col and datasource_col in df.columns:
        out["DataSource"] = (
            df[datasource_col]
            .astype(str)
            .str.strip()
            .str.upper()
        )
        out.loc[
            out["DataSource"].isin(["", "NAN", "NONE"]),
            "DataSource"
        ] = None
    else:
        out["DataSource"] = None
        country_col = column_map.get("country")
    if country_col and country_col in df.columns:
        out["Country"] = (
            df[country_col]
            .astype(str)
            .str.strip()
        )
        out.loc[
            out["Country"].isin(["", "nan", "None", "NaN"]),
            "Country"
        ] = None
    else:
        out["Country"] = None
    before = len(out)
    out = out.dropna(
        subset=["Name", "Ticker"]
    )
    out = out[
        out["Ticker"]
        .astype(str)
        .str.strip()
        .ne("")
    ]
    dropped = before - len(out)
    if dropped:
        logger.warning(
            "read_excel_sheet('%s'): dropped %d row(s) "
            "with missing Name/Ticker.",
            sheet_key,
            dropped
        )
    logger.info(
        "read_excel_sheet('%s'): loaded %d row(s) (%d active).",
        sheet_key,
        len(out),
        int(out["Active"].sum())
    )
    return out.reset_index(drop=True)
# ==========================================================================
# DATA CLEANING
# ==========================================================================
def safe_float(value) -> Optional[float]:
    """
    Convert a value safely to float.
    Returns None for invalid, missing, infinite, or non-numeric values.
    """
    if value is None:
        return None
    try:
        result = float(value)
        if not np.isfinite(result):
            return None
        return result
    except (TypeError, ValueError):
        return None
def safe_numeric(
    series: pd.Series,
    errors: str = "coerce"
) -> pd.Series:
    """
    Convert a pandas Series to numeric safely.
    """
    return pd.to_numeric(
        series,
        errors=errors
    )
# ==========================================================================
# DATE FUNCTIONS
# ==========================================================================
def to_date(value) -> Optional[pd.Timestamp]:
    """
    Convert a date/time value to a timezone-naive normalized pandas Timestamp.
    Handles:
        - datetime
        - date
        - pandas Timestamp
        - timezone-aware timestamps
        - strings
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        return timestamp.normalize()
    except (TypeError, ValueError):
        return None
def convert_date_column(
    df: pd.DataFrame,
    column: str = "Date",
    dayfirst: bool = False
) -> pd.DataFrame:
    """
    Convert a DataFrame date column into normalized datetime values.
    """
    if column not in df.columns:
        raise ValueError(
            f"Date column '{column}' not found."
        )
    result = df.copy()
    result[column] = pd.to_datetime(
        result[column],
        dayfirst=dayfirst,
        errors="coerce"
    )
    try:
        if result[column].dt.tz is not None:
            result[column] = (
                result[column]
                .dt.tz_localize(None)
            )
    except AttributeError:
        pass
    result[column] = result[column].dt.normalize()
    return result
def last_completed_trading_date(
    dates: Iterable
) -> Optional[pd.Timestamp]:
    """
    Return the latest trading date that is not in the future
    and is not today's active/incomplete session.
    This is important because the dashboard should report the
    last completed market session rather than an incomplete current day.
    """
    cleaned_dates = []
    for value in dates:
        converted = to_date(value)
        if converted is not None:
            cleaned_dates.append(converted)
    if not cleaned_dates:
        return None
    unique_dates = sorted(
        set(cleaned_dates)
    )
    today = pd.Timestamp(
        datetime.now().date()
    )
    completed_dates = [
        value
        for value in unique_dates
        if value < today
    ]
    if not completed_dates:
        return None
    return completed_dates[-1]
# ==========================================================================
# PRICE LOOKUP / RETURN FUNCTIONS
# ==========================================================================
def calculate_pct_change(
    old_price,
    new_price
) -> Optional[float]:
    """
    Calculate percentage change.
    Formula:
        ((new - old) / old) * 100
    Returns None when calculation is not possible.
    """
    old_value = safe_float(old_price)
    new_value = safe_float(new_price)
    if old_value is None or new_value is None:
        return None
    if old_value == 0:
        return None
    return (
        (new_value - old_value)
        / old_value
    ) * 100.0
def get_price_on_or_before(
    closes: pd.Series,
    target_date
) -> Optional[float]:
    """
    Find the latest available closing price on or before target_date.
    This allows the calculation to work correctly when the target
    calendar date was a weekend or market holiday.
    """
    target = to_date(target_date)
    if target is None:
        return None
    series = closes.copy()
    if series.empty:
        return None
    normalized_index = []
    for value in series.index:
        converted = to_date(value)
        normalized_index.append(converted)
    series.index = pd.Index(normalized_index)
    series = series[
        ~series.index.isna()
    ]
    series = series.sort_index()
    eligible = series[
        series.index <= target
    ]
    if eligible.empty:
        return None
    return safe_float(
        eligible.iloc[-1]
    )
# ==========================================================================
# RETURN-PERIOD CALCULATION
# ==========================================================================
def compute_return_periods(
    history: pd.DataFrame
) -> Optional[dict]:
    """
    Calculate the market metrics required by the project.
    Required output:
        CurrentPrice
        MarketDate
        Change1D
        Change1W
        Change1M
        Change3M
        Change6M
        Change1Y
        Change3Y
        Change5Y
    Lookback periods use calendar-day targets and then select the
    latest available trading day on or before that target.
    A missing long-term period does NOT invalidate the entire
    instrument. That individual field becomes None.
    Returns None only when a valid current price cannot be determined.
    """
    if history is None:
        return None
    if history.empty:
        return None
    if "Close" not in history.columns:
        return None
    closes = history["Close"].copy()
    closes = pd.to_numeric(
        closes,
        errors="coerce"
    )
    closes = closes.dropna()
    if closes.empty:
        return None
    normalized_index = []
    for value in closes.index:
        normalized_index.append(
            to_date(value)
        )
    closes.index = pd.Index(
        normalized_index
    )
    closes = closes[
        ~closes.index.isna()
    ]
    closes = closes[
        ~closes.index.duplicated(
            keep="last"
        )
    ]
    closes = closes.sort_index()
    if closes.empty:
        return None
    market_date = last_completed_trading_date(
        closes.index
    )
    if market_date is None:
        return None
    closes_to_date = closes[
        closes.index <= market_date
    ]
    if closes_to_date.empty:
        return None
    current_price = safe_float(
        closes_to_date.iloc[-1]
    )
    if current_price is None:
        return None
    lookbacks = {
        "Change1D": 1,
        "Change1W": 7,
        "Change1M": 30,
        "Change3M": 91,
        "Change6M": 182,
        "Change1Y": 365,
        "Change3Y": 365 * 3,
        "Change5Y": 365 * 5
    }
    result = {
        "CurrentPrice": current_price,
        "MarketDate": market_date
    }
    for label, days_back in lookbacks.items():
        target_date = (
            market_date
            - pd.Timedelta(days=days_back)
        )
        old_price = get_price_on_or_before(
            closes_to_date,
            target_date
        )
        result[label] = calculate_pct_change(
            old_price,
            current_price
        )
    return result
# ==========================================================================
# YFINANCE DATA DOWNLOAD
# ==========================================================================
def _normalise_yfinance_columns(
    df: pd.DataFrame,
    ticker: str
) -> pd.DataFrame:
    """
    Normalize columns returned by yfinance.
    YFinance can return:
        Open
        High
        Low
        Close
        Adj Close
        Volume
    but newer versions can also return MultiIndex columns.
    This function converts the result into a simple DataFrame with
    standard OHLCV column names.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    result = df.copy()
    if isinstance(result.columns, pd.MultiIndex):
        flattened = []
        for column in result.columns:
            parts = [
                str(part)
                for part in column
                if str(part).strip()
            ]
            if not parts:
                flattened.append("")
                continue
            if ticker in parts:
                parts.remove(ticker)
            flattened.append(parts[0])
        result.columns = flattened
    result.columns = [
        str(column).strip()
        for column in result.columns
    ]
    rename_map = {}
    for column in result.columns:
        normalized = column.lower().strip()
        if normalized == "open":
            rename_map[column] = "Open"
        elif normalized == "high":
            rename_map[column] = "High"
        elif normalized == "low":
            rename_map[column] = "Low"
        elif normalized == "close":
            rename_map[column] = "Close"
        elif normalized == "adj close":
            rename_map[column] = "Adj Close"
        elif normalized == "volume":
            rename_map[column] = "Volume"
    result = result.rename(
        columns=rename_map
    )
    if "Close" not in result.columns:
        return pd.DataFrame()
    if not isinstance(result.index, pd.DatetimeIndex):
        result.index = pd.to_datetime(
            result.index,
            errors="coerce"
        )
    try:
        if result.index.tz is not None:
            result.index = (
                result.index
                .tz_localize(None)
            )
    except AttributeError:
        pass
    result.index = result.index.normalize()
    result = result[
        ~result.index.isna()
    ]
    result["Close"] = pd.to_numeric(
        result["Close"],
        errors="coerce"
    )
    for column in (
        "Open",
        "High",
        "Low",
        "Adj Close",
        "Volume"
    ):
        if column in result.columns:
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce"
            )
    result = result.dropna(
        subset=["Close"]
    )
    result = result[
        ~result.index.duplicated(
            keep="last"
        )
    ]
    result = result.sort_index()
    return result
def download_ticker_history(
    ticker: str,
    years: int = 6,
    retries: int = 3
) -> Optional[pd.DataFrame]:
    """
    Download daily historical data from Yahoo Finance.
    This function is intended for:
        - Global Markets
        - Assets
        - Other instruments that use YFinance
    It intentionally does NOT handle Jugaad/NSELIB.
    Six years of data are requested by default because the project
    requires a 5-year return period plus enough buffer.
    Returns:
        Clean OHLCV DataFrame with a DatetimeIndex,
        or None if downloading fails.
    """
    ticker = clean_ticker(ticker)
    if not ticker:
        logger.error(
            "download_ticker_history(): empty ticker."
        )
        return None
    today = datetime.now().date()
    start_date = (
        today
        - timedelta(days=365 * years)
    )
    end_date = (
        today
        + timedelta(days=1)
    )
    last_exception = None
    for attempt in range(
        1,
        retries + 1
    ):
        try:
            logger.info(
                "Yahoo: downloading '%s' from %s to %s.",
                ticker,
                start_date,
                end_date
            )
            data = yf.download(
                ticker,
                start=start_date,
                end=end_date,
                interval="1d",
                auto_adjust=False,
                progress=False,
                actions=False,
                threads=False
            )
            cleaned = _normalise_yfinance_columns(
                data,
                ticker
            )
            if cleaned.empty:
                raise ValueError(
                    "Yahoo Finance returned no usable data."
                )
            logger.info(
                "Yahoo: '%s' returned %d usable rows. "
                "Oldest=%s, Latest=%s.",
                ticker,
                len(cleaned),
                cleaned.index.min().date(),
                cleaned.index.max().date()
            )
            return cleaned
        except Exception as exc:
            last_exception = exc
            logger.warning(
                "Yahoo: attempt %d/%d failed for '%s': %s",
                attempt,
                retries,
                ticker,
                exc
            )
            if attempt < retries:
                time.sleep(
                    getattr(
                        CONFIG,
                        "SLEEP_TIME",
                        2
                    )
                )
    logger.error(
        "Yahoo: failed to download '%s' after %d attempt(s): %s",
        ticker,
        retries,
        last_exception
    )
    return None
# ==========================================================================
# GENERIC RETRY UTILITY
# ==========================================================================
def retry_operation(
    operation: Callable[[], T],
    retries: int = 3,
    delay: float = 2.0,
    operation_name: str = "operation"
) -> Optional[T]:
    """
    Execute a callable with retry logic.
    Example:
        result = retry_operation(
            lambda: some_function(),
            retries=3,
            delay=2,
            operation_name="download data"
        )
    """
    last_exception = None
    for attempt in range(
        1,
        retries + 1
    ):
        try:
            return operation()
        except Exception as exc:
            last_exception = exc
            logger.warning(
                "%s failed on attempt %d/%d: %s",
                operation_name,
                attempt,
                retries,
                exc
            )
            if attempt < retries:
                time.sleep(delay)
    logger.error(
        "%s failed after %d attempt(s): %s",
        operation_name,
        retries,
        last_exception
    )
    return None
# ==========================================================================
# SIMPLE DATAFRAME CLEANING UTILITIES
# ==========================================================================
def clean_ohlc_dataframe(
    df: pd.DataFrame
) -> pd.DataFrame:
    """
    Clean a standard OHLC DataFrame.
    Expected columns:
        Open
        High
        Low
        Close
    """
    if df is None or df.empty:
        return pd.DataFrame()
    result = df.copy()
    if "Date" in result.columns:
        result["Date"] = pd.to_datetime(
            result["Date"],
            errors="coerce"
        )
        result = result.dropna(
            subset=["Date"]
        )
        result = result.sort_values(
            "Date"
        )
        result = result.set_index(
            "Date"
        )
    for column in (
        "Open",
        "High",
        "Low",
        "Close",
        "Adj Close",
        "Volume"
    ):
        if column in result.columns:
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce"
            )
    if "Close" in result.columns:
        result = result.dropna(
            subset=["Close"]
        )
    return result
def format_percentage(value) -> Optional[float]:
    """
    Safely format a percentage value for downstream use.
    The database layer can store the returned float directly.
    """
    return safe_float(value)
# ==========================================================================
# MANUAL TEST
# ==========================================================================
if __name__ == "__main__":
    print("Testing utils.helpers...")
    try:
        print("\nTesting Excel sheet loading:")
        for key in CONFIG.EXCEL_SHEETS:
            try:
                frame = read_excel_sheet(key)
                print(
                    f"{key}: "
                    f"{len(frame)} row(s), "
                    f"{int(frame['Active'].sum())} active"
                )
            except Exception as exc:
                print(
                    f"{key}: FAILED - {exc}"
                )
        print("\nTesting helper functions completed.")
    except Exception as exc:
        print(
            f"helpers.py test failed: {exc}"
        )