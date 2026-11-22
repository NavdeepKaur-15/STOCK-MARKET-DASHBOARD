# """
# calculations/technical_indicators.py

# Calculates technical indicators for:
#     - Indian market indices
#     - Global market indices
#     - Assets

# The SQL table uses:
#     PRIMARY KEY (Category, Ticker)

# Therefore the same ticker may safely exist in different categories.

# Calculated indicators:
#     - CurrentPrice
#     - SMA20
#     - SMA100
#     - SMA200
#     - RSI14
#     - MACD
#     - MACDSignal
#     - MACDHistogram
#     - BollingerMiddle
#     - BollingerUpper
#     - BollingerLower
#     - MarketDate

# Data sources:
#     - Indian indices: Jugaad Data / NSE historical index data
#     - Global markets: yfinance
#     - Assets: yfinance

# This file does NOT:
#     - create SQL tables
#     - insert data into SQL
#     - delete SQL rows
#     - create a Power BI dashboard
#     - calculate strength scores
#     - calculate market sentiment
# """

# from __future__ import annotations

# import logging
# from datetime import date, datetime, timedelta

# import numpy as np
# import pandas as pd
# import yfinance as yf

# try:
#     import jugaad_data.nse as jugaad_nse
# except ImportError:
#     jugaad_nse = None

# from utils.helpers import read_excel_sheet, setup_logging

# logger = setup_logging()


# # ============================================================
# # SETTINGS
# # ============================================================

# HISTORY_YEARS = 6
# MINIMUM_ROWS = 200

# # INDIAN_CATEGORY = "Indian"
# INDIAN_CATEGORY = "MarketIndices"
# GLOBAL_CATEGORY = "Global"
# ASSET_CATEGORY = "Asset"


# # ============================================================
# # INDIAN INDEX MAPPING
# # ============================================================

# # Jugaad/NSE names corresponding to the Indian market indices
# # used by this project.

# INDIAN_INDEX_MAP = {
#     "Nifty 50": "NIFTY 50",
#     "Nifty 100": "NIFTY 100",
#     "Nifty 500": "NIFTY 500",
#     "Nifty Midcap 50": "NIFTY MIDCAP 50",
#     "Nifty Midcap 150": "NIFTY MIDCAP 150",
#     "Nifty Smallcap 100": "NIFTY SMALLCAP 100",
#     "Nifty Smallcap 250": "NIFTY SMALLCAP 250",
#     "Nifty Microcap 250": "NIFTY MICROCAP 250",
# }


# # ============================================================
# # GENERAL HELPERS
# # ============================================================

# def _normalise_date(value):
#     """Convert a value to a Python date."""
#     if value is None:
#         return None

#     if isinstance(value, datetime):
#         return value.date()

#     if isinstance(value, date):
#         return value

#     try:
#         converted = pd.to_datetime(value, errors="coerce")
#         if pd.isna(converted):
#             return None
#         return converted.date()
#     except Exception:
#         return None


# def _clean_numeric_series(series):
#     """Convert a pandas series to numeric values."""
#     return pd.to_numeric(series, errors="coerce")


# def _prepare_history(df):
#     """
#     Standardise historical data into:

#         Date
#         Close

#     Works with different column naming conventions used by
#     Jugaad Data and yfinance.
#     """
#     if df is None or df.empty:
#         return pd.DataFrame()

#     data = df.copy()

#     # --------------------------------------------------------
#     # Flatten MultiIndex columns if yfinance returns them.
#     # --------------------------------------------------------
#     if isinstance(data.columns, pd.MultiIndex):
#         flattened = []

#         for column in data.columns:
#             if isinstance(column, tuple):
#                 selected = None

#                 for item in column:
#                     if str(item).lower() in {
#                         "open",
#                         "high",
#                         "low",
#                         "close",
#                         "adj close",
#                         "volume",
#                         "date",
#                     }:
#                         selected = item
#                         break

#                 flattened.append(
#                     selected if selected is not None else str(column[0])
#                 )
#             else:
#                 flattened.append(str(column))

#         data.columns = flattened

#     # --------------------------------------------------------
#     # Find date column.
#     # --------------------------------------------------------
#     date_column = None

#     possible_date_columns = [
#         "Date",
#         "DATE",
#         "HistoricalDate",
#         "TIMESTAMP",
#         "Datetime",
#         "DateTime",
#     ]

#     for column in possible_date_columns:
#         if column in data.columns:
#             date_column = column
#             break

#     # Sometimes Date is the index.
#     if date_column is None:
#         if isinstance(data.index, pd.DatetimeIndex):
#             data = data.reset_index()
#             date_column = data.columns[0]

#     if date_column is None:
#         logger.error("technical_indicators: historical data has no date column.")
#         return pd.DataFrame()

#     # --------------------------------------------------------
#     # Find close column.
#     # --------------------------------------------------------
#     close_column = None

#     possible_close_columns = [
#         "Close",
#         "CLOSE",
#         "CLOSE_INDEX_VAL",
#         "close",
#     ]

#     for column in possible_close_columns:
#         if column in data.columns:
#             close_column = column
#             break

#     if close_column is None:
#         logger.error(
#             "technical_indicators: historical data has no Close column. "
#             "Available columns: %s",
#             list(data.columns),
#         )
#         return pd.DataFrame()

#     result = pd.DataFrame()

#     result["Date"] = pd.to_datetime(
#         data[date_column],
#         errors="coerce",
#         dayfirst=True,
#     )

#     result["Close"] = _clean_numeric_series(data[close_column])

#     result = result.dropna(subset=["Date", "Close"])

#     result["Date"] = result["Date"].dt.tz_localize(None)

#     result = result.sort_values("Date")
#     result = result.drop_duplicates(subset=["Date"], keep="last")
#     result = result.reset_index(drop=True)

#     return result


# # ============================================================
# # JUGAAD DATA
# # ============================================================

# def _download_indian_history(index_name, from_date, to_date):
#     """
#     Download Indian index history using jugaad_data.

#     Uses index_df() directly rather than NSEIndexHistory.index_df(),
#     because index_df is a module-level function in the installed
#     version of jugaad_data.
#     """
#     if jugaad_nse is None:
#         logger.error(
#             "Jugaad Data is not installed. "
#             "Install it using: pip install jugaad-data"
#         )
#         return pd.DataFrame()

#     try:
#         logger.info(
#             "Jugaad: downloading '%s' from %s to %s.",
#             index_name,
#             from_date,
#             to_date,
#         )

#         raw = jugaad_nse.index_df(
#             index_name,
#             from_date,
#             to_date,
#         )

#         if raw is None or raw.empty:
#             logger.error(
#                 "Jugaad: no data returned for '%s'.",
#                 index_name,
#             )
#             return pd.DataFrame()

#         history = _prepare_history(raw)

#         if history.empty:
#             logger.error(
#                 "Jugaad: returned data for '%s' could not be converted.",
#                 index_name,
#             )
#             return pd.DataFrame()

#         logger.info(
#             "Jugaad: '%s' returned %d usable rows. Oldest=%s, Latest=%s.",
#             index_name,
#             len(history),
#             history["Date"].min().date(),
#             history["Date"].max().date(),
#         )

#         return history

#     except Exception as exc:
#         logger.error(
#             "Jugaad: failed for '%s': %s",
#             index_name,
#             exc,
#         )
#         return pd.DataFrame()


# # ============================================================
# # YAHOO FINANCE
# # ============================================================

# def _download_yahoo_history(ticker, from_date, to_date):
#     """Download historical data using yfinance."""
#     try:
#         logger.info(
#             "Yahoo: downloading '%s' from %s to %s.",
#             ticker,
#             from_date,
#             to_date,
#         )

#         # yfinance end date is exclusive, so add one day.
#         yahoo_end = to_date + timedelta(days=1)

#         data = yf.download(
#             ticker,
#             start=from_date,
#             end=yahoo_end,
#             interval="1d",
#             auto_adjust=False,
#             progress=False,
#             actions=False,
#         )

#         if data is None or data.empty:
#             logger.error(
#                 "Yahoo: no data returned for '%s'.",
#                 ticker,
#             )
#             return pd.DataFrame()

#         history = _prepare_history(data)

#         if history.empty:
#             logger.error(
#                 "Yahoo: '%s' returned data but it could not be prepared.",
#                 ticker,
#             )
#             return pd.DataFrame()

#         logger.info(
#             "Yahoo: '%s' returned %d usable rows. Oldest=%s, Latest=%s.",
#             ticker,
#             len(history),
#             history["Date"].min().date(),
#             history["Date"].max().date(),
#         )

#         return history

#     except Exception as exc:
#         logger.error(
#             "Yahoo: failed for '%s': %s",
#             ticker,
#             exc,
#         )
#         return pd.DataFrame()


# # ============================================================
# # TECHNICAL CALCULATIONS
# # ============================================================

# def _calculate_indicators(history):
#     """
#     Calculate all technical indicators required by the
#     TechnicalIndicators SQL table.
#     """
#     if history is None or history.empty:
#         return None

#     df = history.copy()

#     if len(df) < MINIMUM_ROWS:
#         logger.warning(
#             "Technical calculation skipped: only %d rows available; "
#             "%d required.",
#             len(df),
#             MINIMUM_ROWS,
#         )
#         return None

#     close = df["Close"].astype(float)

#     # --------------------------------------------------------
#     # SMA
#     # --------------------------------------------------------
#     df["SMA20"] = close.rolling(
#         window=20,
#         min_periods=20,
#     ).mean()

#     df["SMA100"] = close.rolling(
#         window=100,
#         min_periods=100,
#     ).mean()

#     df["SMA200"] = close.rolling(
#         window=200,
#         min_periods=200,
#     ).mean()

#     # --------------------------------------------------------
#     # RSI 14
#     # --------------------------------------------------------
#     delta = close.diff()

#     gain = delta.clip(lower=0)
#     loss = -delta.clip(upper=0)

#     average_gain = gain.ewm(
#         alpha=1 / 14,
#         min_periods=14,
#         adjust=False,
#     ).mean()

#     average_loss = loss.ewm(
#         alpha=1 / 14,
#         min_periods=14,
#         adjust=False,
#     ).mean()

#     rs = average_gain / average_loss.replace(0, np.nan)

#     df["RSI14"] = 100 - (100 / (1 + rs))

#     # Handle periods where there is no loss.
#     df.loc[
#         (average_loss == 0) & (average_gain > 0),
#         "RSI14",
#     ] = 100

#     # --------------------------------------------------------
#     # MACD
#     # Standard:
#     # Fast EMA = 12
#     # Slow EMA = 26
#     # Signal = 9
#     # --------------------------------------------------------
#     ema12 = close.ewm(
#         span=12,
#         adjust=False,
#         min_periods=12,
#     ).mean()

#     ema26 = close.ewm(
#         span=26,
#         adjust=False,
#         min_periods=26,
#     ).mean()

#     df["MACD"] = ema12 - ema26

#     df["MACDSignal"] = df["MACD"].ewm(
#         span=9,
#         adjust=False,
#         min_periods=9,
#     ).mean()

#     df["MACDHistogram"] = (
#         df["MACD"] - df["MACDSignal"]
#     )

#     # --------------------------------------------------------
#     # Bollinger Bands
#     # Standard 20-period / 2 standard deviations
#     # --------------------------------------------------------
#     df["BollingerMiddle"] = close.rolling(
#         window=20,
#         min_periods=20,
#     ).mean()

#     rolling_std = close.rolling(
#         window=20,
#         min_periods=20,
#     ).std()

#     df["BollingerUpper"] = (
#         df["BollingerMiddle"] + (2 * rolling_std)
#     )

#     df["BollingerLower"] = (
#         df["BollingerMiddle"] - (2 * rolling_std)
#     )

#     # --------------------------------------------------------
#     # Latest completed trading row
#     # --------------------------------------------------------
#     df = df.dropna(subset=["Close"])

#     if df.empty:
#         return None

#     latest = df.iloc[-1]

#     return {
#         "CurrentPrice": float(latest["Close"]),
#         "SMA20": _safe_float(latest["SMA20"]),
#         "SMA100": _safe_float(latest["SMA100"]),
#         "SMA200": _safe_float(latest["SMA200"]),
#         "RSI14": _safe_float(latest["RSI14"]),
#         "MACD": _safe_float(latest["MACD"]),
#         "MACDSignal": _safe_float(latest["MACDSignal"]),
#         "MACDHistogram": _safe_float(latest["MACDHistogram"]),
#         "BollingerMiddle": _safe_float(
#             latest["BollingerMiddle"]
#         ),
#         "BollingerUpper": _safe_float(
#             latest["BollingerUpper"]
#         ),
#         "BollingerLower": _safe_float(
#             latest["BollingerLower"]
#         ),
#         "MarketDate": latest["Date"].date(),
#     }


# def _safe_float(value):
#     """Convert NaN/invalid values to None."""
#     try:
#         if pd.isna(value):
#             return None
#         return float(value)
#     except Exception:
#         return None


# # ============================================================
# # EXCEL INSTRUMENT LOADING
# # ============================================================

# def _get_active_instruments(sheet_name):
#     """
#     Read an Excel sheet and return active instruments.

#     Expected columns include:
#         Name
#         Ticker
#         Active
#     """
#     try:
#         df = read_excel_sheet(sheet_name)
#     except Exception as exc:
#         logger.error(
#             "technical_indicators: failed to read '%s': %s",
#             sheet_name,
#             exc,
#         )
#         return pd.DataFrame()

#     if df is None or df.empty:
#         logger.warning(
#             "technical_indicators: '%s' sheet is empty.",
#             sheet_name,
#         )
#         return pd.DataFrame()

#     if "Active" in df.columns:
#         active = df[
#             df["Active"].astype(str).str.lower().isin(
#                 ["true", "1", "yes", "y"]
#             )
#         ].copy()
#     else:
#         active = df.copy()

#     return active.reset_index(drop=True)


# # ============================================================
# # SINGLE INSTRUMENT PROCESSING
# # ============================================================

# def _process_instrument(
#     name,
#     ticker,
#     category,
#     from_date,
#     to_date,
# ):
#     """Download history and calculate indicators for one instrument."""

#     logger.info(
#         "Technical indicators: processing '%s' (%s) [%s].",
#         name,
#         ticker,
#         category,
#     )

#     # --------------------------------------------------------
#     # Indian indices use Jugaad.
#     # --------------------------------------------------------
#     if category == INDIAN_CATEGORY:
#         jugaad_name = INDIAN_INDEX_MAP.get(name)

#         if not jugaad_name:
#             logger.error(
#                 "No Jugaad index mapping found for '%s'.",
#                 name,
#             )
#             return None

#         history = _download_indian_history(
#             jugaad_name,
#             from_date,
#             to_date,
#         )

#     # --------------------------------------------------------
#     # Global markets and assets use Yahoo Finance.
#     # --------------------------------------------------------
#     else:
#         history = _download_yahoo_history(
#             ticker,
#             from_date,
#             to_date,
#         )

#     if history is None or history.empty:
#         logger.error(
#             "Technical indicators: no historical data for '%s'.",
#             name,
#         )
#         return None

#     metrics = _calculate_indicators(history)

#     if metrics is None:
#         logger.error(
#             "Technical indicators: calculation failed for '%s'.",
#             name,
#         )
#         return None

#     return {
#         "Ticker": ticker,
#         "Category": category,
#         "CurrentPrice": metrics["CurrentPrice"],
#         "SMA20": metrics["SMA20"],
#         "SMA100": metrics["SMA100"],
#         "SMA200": metrics["SMA200"],
#         "RSI14": metrics["RSI14"],
#         "MACD": metrics["MACD"],
#         "MACDSignal": metrics["MACDSignal"],
#         "MACDHistogram": metrics["MACDHistogram"],
#         "BollingerMiddle": metrics["BollingerMiddle"],
#         "BollingerUpper": metrics["BollingerUpper"],
#         "BollingerLower": metrics["BollingerLower"],
#         "MarketDate": metrics["MarketDate"],
#     }


# # ============================================================
# # MAIN FUNCTION
# # ============================================================

# def fetch_technical_indicators_data():
#     """
#     Download historical data and return one consolidated
#     DataFrame suitable for dbo.TechnicalIndicators.

#     The resulting DataFrame contains:

#         Ticker
#         Category
#         CurrentPrice
#         SMA20
#         SMA100
#         SMA200
#         RSI14
#         MACD
#         MACDSignal
#         MACDHistogram
#         BollingerMiddle
#         BollingerUpper
#         BollingerLower
#         MarketDate
#     """

#     today = date.today()
#     from_date = today - timedelta(days=HISTORY_YEARS * 365)
#     to_date = today

#     rows = []

#     # --------------------------------------------------------
#     # 1. INDIAN MARKET INDICES
#     # --------------------------------------------------------
#     indian = _get_active_instruments("market_indices")

#     if not indian.empty:
#         for _, row in indian.iterrows():
#             name = str(row["Name"]).strip()
#             ticker = str(row["Ticker"]).strip()

#             result = _process_instrument(
#                 name=name,
#                 ticker=ticker,
#                 category=INDIAN_CATEGORY,
#                 from_date=from_date,
#                 to_date=to_date,
#             )

#             if result is not None:
#                 rows.append(result)

#     # --------------------------------------------------------
#     # 2. GLOBAL MARKETS
#     # --------------------------------------------------------
#     global_markets = _get_active_instruments("global_markets")

#     if not global_markets.empty:
#         for _, row in global_markets.iterrows():
#             name = str(row["Name"]).strip()
#             ticker = str(row["Ticker"]).strip()

#             result = _process_instrument(
#                 name=name,
#                 ticker=ticker,
#                 category=GLOBAL_CATEGORY,
#                 from_date=from_date,
#                 to_date=to_date,
#             )

#             if result is not None:
#                 rows.append(result)

#     # --------------------------------------------------------
#     # 3. ASSETS
#     # --------------------------------------------------------
#     assets = _get_active_instruments("assets")

#     if not assets.empty:
#         for _, row in assets.iterrows():
#             name = str(row["Name"]).strip()
#             ticker = str(row["Ticker"]).strip()

#             result = _process_instrument(
#                 name=name,
#                 ticker=ticker,
#                 category=ASSET_CATEGORY,
#                 from_date=from_date,
#                 to_date=to_date,
#             )

#             if result is not None:
#                 rows.append(result)

#     result_df = pd.DataFrame(rows)

#     if result_df.empty:
#         logger.error(
#             "fetch_technical_indicators_data(): no technical indicator data generated."
#         )
#         return pd.DataFrame()

#     # --------------------------------------------------------
#     # Safety check for the new composite primary key.
#     # --------------------------------------------------------
#     duplicate_mask = result_df.duplicated(
#         subset=["Category", "Ticker"],
#         keep=False,
#     )

#     if duplicate_mask.any():
#         duplicates = result_df.loc[
#             duplicate_mask,
#             ["Category", "Ticker"],
#         ].drop_duplicates()

#         logger.warning(
#             "Duplicate (Category, Ticker) combinations detected:\n%s",
#             duplicates.to_string(index=False),
#         )

#         result_df = result_df.drop_duplicates(
#             subset=["Category", "Ticker"],
#             keep="last",
#         )

#     # --------------------------------------------------------
#     # Keep exact SQL column order.
#     # --------------------------------------------------------
#     columns = [
#         "Ticker",
#         "Category",
#         "CurrentPrice",
#         "SMA20",
#         "SMA100",
#         "SMA200",
#         "RSI14",
#         "MACD",
#         "MACDSignal",
#         "MACDHistogram",
#         "BollingerMiddle",
#         "BollingerUpper",
#         "BollingerLower",
#         "MarketDate",
#     ]

#     result_df = result_df[columns]

#     logger.info(
#         "fetch_technical_indicators_data(): generated %d rows.",
#         len(result_df),
#     )

#     return result_df


# # ============================================================
# # COMPATIBILITY ALIASES
# # ============================================================

# def calculate_technical_indicators():
#     """Compatibility wrapper for existing project code."""
#     return fetch_technical_indicators_data()


# def generate_technical_indicators():
#     """Compatibility wrapper for existing project code."""
#     return fetch_technical_indicators_data()


# # ============================================================
# # DIRECT TEST
# # ============================================================

# if __name__ == "__main__":
#     print("Running technical indicators downloader test...")

#     df_result = fetch_technical_indicators_data()

#     if df_result.empty:
#         print("\nNo technical indicator data returned.")
#     else:
#         print("\nTechnical Indicators Data:")
#         print(df_result.to_string(index=False))

#         print("\nRows:", len(df_result))

#         print("\nRows by Category:")
#         print(
#             df_result["Category"]
#             .value_counts()
#             .to_string()
#         )

#         print("\nPrimary-key check:")
#         duplicate_count = df_result.duplicated(
#             subset=["Category", "Ticker"]
#         ).sum()

#         print(
#             "Duplicate (Category, Ticker) rows:",
#             duplicate_count,
#         )

# def get_market_indices_technical_indicators() -> pd.DataFrame:
#     df = fetch_technical_indicators_data()
#     if df.empty:
#         return df
#     return df[df["Category"].eq("MarketIndices")].reset_index(drop=True)

# def get_global_markets_technical_indicators() -> pd.DataFrame:
#     df = fetch_technical_indicators_data()
#     if df.empty:
#         return df
#     return df[df["Category"].eq("GlobalMarkets")].reset_index(drop=True)

# def get_assets_technical_indicators() -> pd.DataFrame:
#     df = fetch_technical_indicators_data()
#     if df.empty:
#         return df
#     return df[df["Category"].eq("Assets")].reset_index(drop=True)
"""
calculations/technical_indicators.py

Calculates technical indicators for:
    - Indian market indices
    - Global market indices
    - Assets

The SQL table uses:
    PRIMARY KEY (Category, Ticker)

Therefore the same ticker may safely exist in different categories.

Calculated indicators:
    - CurrentPrice
    - SMA20
    - SMA100
    - SMA200
    - RSI14
    - MACD
    - MACDSignal
    - MACDHistogram
    - BollingerMiddle
    - BollingerUpper
    - BollingerLower
    - MarketDate

Data sources:
    - Indian indices: Jugaad Data / NSE historical index data
    - Global markets: yfinance
    - Assets: yfinance

This file does NOT:
    - create SQL tables
    - insert data into SQL
    - delete SQL rows
    - create a Power BI dashboard
    - calculate strength scores
    - calculate market sentiment
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

try:
    import jugaad_data.nse as jugaad_nse
except ImportError:
    jugaad_nse = None

from utils.helpers import read_excel_sheet, setup_logging

logger = setup_logging()


# ============================================================
# SETTINGS
# ============================================================

HISTORY_YEARS = 6
MINIMUM_ROWS = 200

# INDIAN_CATEGORY = "Indian"
INDIAN_CATEGORY = "MarketIndices"
GLOBAL_CATEGORY = "Global"
ASSET_CATEGORY = "Asset"


# ============================================================
# INDIAN INDEX MAPPING
# ============================================================

# Jugaad/NSE names corresponding to the Indian market indices
# used by this project.

INDIAN_INDEX_MAP = {
    "Nifty 50": "NIFTY 50",
    "Nifty 100": "NIFTY 100",
    "Nifty 500": "NIFTY 500",
    "Nifty Midcap 50": "NIFTY MIDCAP 50",
    "Nifty Midcap 150": "NIFTY MIDCAP 150",
    "Nifty Smallcap 100": "NIFTY SMALLCAP 100",
    "Nifty Smallcap 250": "NIFTY SMALLCAP 250",
    "Nifty Microcap 250": "NIFTY MICROCAP 250",
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def _normalise_date(value):
    """Convert a value to a Python date."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    try:
        converted = pd.to_datetime(value, errors="coerce")
        if pd.isna(converted):
            return None
        return converted.date()
    except Exception:
        return None


def _clean_numeric_series(series):
    """Convert a pandas series to numeric values."""
    return pd.to_numeric(series, errors="coerce")


def _prepare_history(df):
    """
    Standardise historical data into:

        Date
        Close

    Works with different column naming conventions used by
    Jugaad Data and yfinance.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    data = df.copy()

    # --------------------------------------------------------
    # Flatten MultiIndex columns if yfinance returns them.
    # --------------------------------------------------------
    if isinstance(data.columns, pd.MultiIndex):
        flattened = []

        for column in data.columns:
            if isinstance(column, tuple):
                selected = None

                for item in column:
                    if str(item).lower() in {
                        "open",
                        "high",
                        "low",
                        "close",
                        "adj close",
                        "volume",
                        "date",
                    }:
                        selected = item
                        break

                flattened.append(
                    selected if selected is not None else str(column[0])
                )
            else:
                flattened.append(str(column))

        data.columns = flattened

    # --------------------------------------------------------
    # Find date column.
    # --------------------------------------------------------
    date_column = None

    possible_date_columns = [
        "Date",
        "DATE",
        "HistoricalDate",
        "TIMESTAMP",
        "Datetime",
        "DateTime",
    ]

    for column in possible_date_columns:
        if column in data.columns:
            date_column = column
            break

    # Sometimes Date is the index.
    if date_column is None:
        if isinstance(data.index, pd.DatetimeIndex):
            data = data.reset_index()
            date_column = data.columns[0]

    if date_column is None:
        logger.error("technical_indicators: historical data has no date column.")
        return pd.DataFrame()

    # --------------------------------------------------------
    # Find close column.
    # --------------------------------------------------------
    close_column = None

    possible_close_columns = [
        "Close",
        "CLOSE",
        "CLOSE_INDEX_VAL",
        "close",
    ]

    for column in possible_close_columns:
        if column in data.columns:
            close_column = column
            break

    if close_column is None:
        logger.error(
            "technical_indicators: historical data has no Close column. "
            "Available columns: %s",
            list(data.columns),
        )
        return pd.DataFrame()

    result = pd.DataFrame()

    result["Date"] = pd.to_datetime(
        data[date_column],
        errors="coerce",
        dayfirst=True,
    )

    result["Close"] = _clean_numeric_series(data[close_column])

    result = result.dropna(subset=["Date", "Close"])

    result["Date"] = result["Date"].dt.tz_localize(None)

    result = result.sort_values("Date")
    result = result.drop_duplicates(subset=["Date"], keep="last")
    result = result.reset_index(drop=True)

    return result


# ============================================================
# JUGAAD DATA
# ============================================================

def _download_indian_history(index_name, from_date, to_date):
    """
    Download Indian index history using jugaad_data.

    Uses index_df() directly rather than NSEIndexHistory.index_df(),
    because index_df is a module-level function in the installed
    version of jugaad_data.
    """
    if jugaad_nse is None:
        logger.error(
            "Jugaad Data is not installed. "
            "Install it using: pip install jugaad-data"
        )
        return pd.DataFrame()

    try:
        logger.info(
            "Jugaad: downloading '%s' from %s to %s.",
            index_name,
            from_date,
            to_date,
        )

        raw = jugaad_nse.index_df(
            index_name,
            from_date,
            to_date,
        )

        if raw is None or raw.empty:
            logger.error(
                "Jugaad: no data returned for '%s'.",
                index_name,
            )
            return pd.DataFrame()

        history = _prepare_history(raw)

        if history.empty:
            logger.error(
                "Jugaad: returned data for '%s' could not be converted.",
                index_name,
            )
            return pd.DataFrame()

        logger.info(
            "Jugaad: '%s' returned %d usable rows. Oldest=%s, Latest=%s.",
            index_name,
            len(history),
            history["Date"].min().date(),
            history["Date"].max().date(),
        )

        return history

    except Exception as exc:
        logger.error(
            "Jugaad: failed for '%s': %s",
            index_name,
            exc,
        )
        return pd.DataFrame()


# ============================================================
# YAHOO FINANCE
# ============================================================

def _download_yahoo_history(ticker, from_date, to_date):
    """Download historical data using yfinance."""
    try:
        logger.info(
            "Yahoo: downloading '%s' from %s to %s.",
            ticker,
            from_date,
            to_date,
        )

        # yfinance end date is exclusive, so add one day.
        yahoo_end = to_date + timedelta(days=1)

        data = yf.download(
            ticker,
            start=from_date,
            end=yahoo_end,
            interval="1d",
            auto_adjust=False,
            progress=False,
            actions=False,
        )

        if data is None or data.empty:
            logger.error(
                "Yahoo: no data returned for '%s'.",
                ticker,
            )
            return pd.DataFrame()

        history = _prepare_history(data)

        if history.empty:
            logger.error(
                "Yahoo: '%s' returned data but it could not be prepared.",
                ticker,
            )
            return pd.DataFrame()

        logger.info(
            "Yahoo: '%s' returned %d usable rows. Oldest=%s, Latest=%s.",
            ticker,
            len(history),
            history["Date"].min().date(),
            history["Date"].max().date(),
        )

        return history

    except Exception as exc:
        logger.error(
            "Yahoo: failed for '%s': %s",
            ticker,
            exc,
        )
        return pd.DataFrame()


# ============================================================
# TECHNICAL CALCULATIONS
# ============================================================

def _calculate_indicators(history):
    """
    Calculate all technical indicators required by the
    TechnicalIndicators SQL table.
    """
    if history is None or history.empty:
        return None

    df = history.copy()

    if len(df) < MINIMUM_ROWS:
        logger.warning(
            "Technical calculation skipped: only %d rows available; "
            "%d required.",
            len(df),
            MINIMUM_ROWS,
        )
        return None

    close = df["Close"].astype(float)

    # --------------------------------------------------------
    # SMA
    # --------------------------------------------------------
    df["SMA20"] = close.rolling(
        window=20,
        min_periods=20,
    ).mean()

    df["SMA100"] = close.rolling(
        window=100,
        min_periods=100,
    ).mean()

    df["SMA200"] = close.rolling(
        window=200,
        min_periods=200,
    ).mean()

    # --------------------------------------------------------
    # RSI 14
    # --------------------------------------------------------
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    average_gain = gain.ewm(
        alpha=1 / 14,
        min_periods=14,
        adjust=False,
    ).mean()

    average_loss = loss.ewm(
        alpha=1 / 14,
        min_periods=14,
        adjust=False,
    ).mean()

    rs = average_gain / average_loss.replace(0, np.nan)

    df["RSI14"] = 100 - (100 / (1 + rs))

    # Handle periods where there is no loss.
    df.loc[
        (average_loss == 0) & (average_gain > 0),
        "RSI14",
    ] = 100

    # --------------------------------------------------------
    # MACD
    # Standard:
    # Fast EMA = 12
    # Slow EMA = 26
    # Signal = 9
    # --------------------------------------------------------
    ema12 = close.ewm(
        span=12,
        adjust=False,
        min_periods=12,
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False,
        min_periods=26,
    ).mean()

    df["MACD"] = ema12 - ema26

    df["MACDSignal"] = df["MACD"].ewm(
        span=9,
        adjust=False,
        min_periods=9,
    ).mean()

    df["MACDHistogram"] = (
        df["MACD"] - df["MACDSignal"]
    )

    # --------------------------------------------------------
    # Bollinger Bands
    # Standard 20-period / 2 standard deviations
    # --------------------------------------------------------
    df["BollingerMiddle"] = close.rolling(
        window=20,
        min_periods=20,
    ).mean()

    rolling_std = close.rolling(
        window=20,
        min_periods=20,
    ).std()

    df["BollingerUpper"] = (
        df["BollingerMiddle"] + (2 * rolling_std)
    )

    df["BollingerLower"] = (
        df["BollingerMiddle"] - (2 * rolling_std)
    )

    # --------------------------------------------------------
    # Latest completed trading row
    # --------------------------------------------------------
    df = df.dropna(subset=["Close"])

    if df.empty:
        return None

    latest = df.iloc[-1]

    return {
        "CurrentPrice": float(latest["Close"]),
        "SMA20": _safe_float(latest["SMA20"]),
        "SMA100": _safe_float(latest["SMA100"]),
        "SMA200": _safe_float(latest["SMA200"]),
        "RSI14": _safe_float(latest["RSI14"]),
        "MACD": _safe_float(latest["MACD"]),
        "MACDSignal": _safe_float(latest["MACDSignal"]),
        "MACDHistogram": _safe_float(latest["MACDHistogram"]),
        "BollingerMiddle": _safe_float(
            latest["BollingerMiddle"]
        ),
        "BollingerUpper": _safe_float(
            latest["BollingerUpper"]
        ),
        "BollingerLower": _safe_float(
            latest["BollingerLower"]
        ),
        "MarketDate": latest["Date"].date(),
    }


def _safe_float(value):
    """Convert NaN/invalid values to None."""
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


# ============================================================
# EXCEL INSTRUMENT LOADING
# ============================================================

def _get_active_instruments(sheet_name):
    """
    Read an Excel sheet and return active instruments.

    Expected columns include:
        Name
        Ticker
        Active
    """
    try:
        df = read_excel_sheet(sheet_name)
    except Exception as exc:
        logger.error(
            "technical_indicators: failed to read '%s': %s",
            sheet_name,
            exc,
        )
        return pd.DataFrame()

    if df is None or df.empty:
        logger.warning(
            "technical_indicators: '%s' sheet is empty.",
            sheet_name,
        )
        return pd.DataFrame()

    if "Active" in df.columns:
        active = df[
            df["Active"].astype(str).str.lower().isin(
                ["true", "1", "yes", "y"]
            )
        ].copy()
    else:
        active = df.copy()

    return active.reset_index(drop=True)


# ============================================================
# SINGLE INSTRUMENT PROCESSING
# ============================================================

def _process_instrument(
    name,
    ticker,
    category,
    from_date,
    to_date,
):
    """Download history and calculate indicators for one instrument."""

    logger.info(
        "Technical indicators: processing '%s' (%s) [%s].",
        name,
        ticker,
        category,
    )

    # --------------------------------------------------------
    # Indian indices use Jugaad.
    # --------------------------------------------------------
    if category == INDIAN_CATEGORY:
        jugaad_name = INDIAN_INDEX_MAP.get(name)

        if not jugaad_name:
            logger.error(
                "No Jugaad index mapping found for '%s'.",
                name,
            )
            return None

        history = _download_indian_history(
            jugaad_name,
            from_date,
            to_date,
        )

    # --------------------------------------------------------
    # Global markets and assets use Yahoo Finance.
    # --------------------------------------------------------
    else:
        history = _download_yahoo_history(
            ticker,
            from_date,
            to_date,
        )

    if history is None or history.empty:
        logger.error(
            "Technical indicators: no historical data for '%s'.",
            name,
        )
        return None

    metrics = _calculate_indicators(history)

    if metrics is None:
        logger.error(
            "Technical indicators: calculation failed for '%s'.",
            name,
        )
        return None

    return {
        "Ticker": ticker,
        "Name": name,
        "Category": category,
        "CurrentPrice": metrics["CurrentPrice"],
        "SMA20": metrics["SMA20"],
        "SMA100": metrics["SMA100"],
        "SMA200": metrics["SMA200"],
        "RSI14": metrics["RSI14"],
        "MACD": metrics["MACD"],
        "MACDSignal": metrics["MACDSignal"],
        "MACDHistogram": metrics["MACDHistogram"],
        "BollingerMiddle": metrics["BollingerMiddle"],
        "BollingerUpper": metrics["BollingerUpper"],
        "BollingerLower": metrics["BollingerLower"],
        "MarketDate": metrics["MarketDate"],
    }


# ============================================================
# MAIN FUNCTION
# ============================================================

def fetch_technical_indicators_data():
    """
    Download historical data and return one consolidated
    DataFrame suitable for dbo.TechnicalIndicators.

    The resulting DataFrame contains:

        Ticker
        Category
        CurrentPrice
        SMA20
        SMA100
        SMA200
        RSI14
        MACD
        MACDSignal
        MACDHistogram
        BollingerMiddle
        BollingerUpper
        BollingerLower
        MarketDate
    """

    today = date.today()
    from_date = today - timedelta(days=HISTORY_YEARS * 365)
    to_date = today

    rows = []

    # --------------------------------------------------------
    # 1. INDIAN MARKET INDICES
    # --------------------------------------------------------
    indian = _get_active_instruments("market_indices")

    if not indian.empty:
        for _, row in indian.iterrows():
            name = str(row["Name"]).strip()
            ticker = str(row["Ticker"]).strip()

            result = _process_instrument(
                name=name,
                ticker=ticker,
                category=INDIAN_CATEGORY,
                from_date=from_date,
                to_date=to_date,
            )

            if result is not None:
                rows.append(result)

    # --------------------------------------------------------
    # 2. GLOBAL MARKETS
    # --------------------------------------------------------
    global_markets = _get_active_instruments("global_markets")

    if not global_markets.empty:
        for _, row in global_markets.iterrows():
            name = str(row["Name"]).strip()
            ticker = str(row["Ticker"]).strip()

            result = _process_instrument(
                name=name,
                ticker=ticker,
                category=GLOBAL_CATEGORY,
                from_date=from_date,
                to_date=to_date,
            )

            if result is not None:
                rows.append(result)

    # --------------------------------------------------------
    # 3. ASSETS
    # --------------------------------------------------------
    assets = _get_active_instruments("assets")

    if not assets.empty:
        for _, row in assets.iterrows():
            name = str(row["Name"]).strip()
            ticker = str(row["Ticker"]).strip()

            result = _process_instrument(
                name=name,
                ticker=ticker,
                category=ASSET_CATEGORY,
                from_date=from_date,
                to_date=to_date,
            )

            if result is not None:
                rows.append(result)

    result_df = pd.DataFrame(rows)

    if result_df.empty:
        logger.error(
            "fetch_technical_indicators_data(): no technical indicator data generated."
        )
        return pd.DataFrame()

    # --------------------------------------------------------
    # Safety check for the new composite primary key.
    # --------------------------------------------------------
    duplicate_mask = result_df.duplicated(
        subset=["Category", "Ticker"],
        keep=False,
    )

    if duplicate_mask.any():
        duplicates = result_df.loc[
            duplicate_mask,
            ["Category", "Ticker"],
        ].drop_duplicates()

        logger.warning(
            "Duplicate (Category, Ticker) combinations detected:\n%s",
            duplicates.to_string(index=False),
        )

        result_df = result_df.drop_duplicates(
            subset=["Category", "Ticker"],
            keep="last",
        )

    # --------------------------------------------------------
    # Keep exact SQL column order.
    # --------------------------------------------------------
    columns = [
        "Ticker",
        "Name",
        "Category",
        "CurrentPrice",
        "SMA20",
        "SMA100",
        "SMA200",
        "RSI14",
        "MACD",
        "MACDSignal",
        "MACDHistogram",
        "BollingerMiddle",
        "BollingerUpper",
        "BollingerLower",
        "MarketDate",
    ]

    result_df = result_df[columns]

    logger.info(
        "fetch_technical_indicators_data(): generated %d rows.",
        len(result_df),
    )

    return result_df


# ============================================================
# COMPATIBILITY ALIASES
# ============================================================

def calculate_technical_indicators():
    """Compatibility wrapper for existing project code."""
    return fetch_technical_indicators_data()


def generate_technical_indicators():
    """Compatibility wrapper for existing project code."""
    return fetch_technical_indicators_data()


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":
    print("Running technical indicators downloader test...")

    df_result = fetch_technical_indicators_data()

    if df_result.empty:
        print("\nNo technical indicator data returned.")
    else:
        print("\nTechnical Indicators Data:")
        print(df_result.to_string(index=False))

        print("\nRows:", len(df_result))

        print("\nRows by Category:")
        print(
            df_result["Category"]
            .value_counts()
            .to_string()
        )

        print("\nPrimary-key check:")
        duplicate_count = df_result.duplicated(
            subset=["Category", "Ticker"]
        ).sum()

        print(
            "Duplicate (Category, Ticker) rows:",
            duplicate_count,
        )

def get_market_indices_technical_indicators() -> pd.DataFrame:
    df = fetch_technical_indicators_data()
    if df.empty:
        return df
    return df[df["Category"].eq(INDIAN_CATEGORY)].reset_index(drop=True)

def get_global_markets_technical_indicators() -> pd.DataFrame:
    df = fetch_technical_indicators_data()
    if df.empty:
        return df
    return df[df["Category"].eq(GLOBAL_CATEGORY)].reset_index(drop=True)

def get_assets_technical_indicators() -> pd.DataFrame:
    df = fetch_technical_indicators_data()
    if df.empty:
        return df
    return df[df["Category"].eq(ASSET_CATEGORY)].reset_index(drop=True)