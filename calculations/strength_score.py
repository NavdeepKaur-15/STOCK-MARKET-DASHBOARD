# """
# calculations/strength_score.py

# STEP 8 of the STOCK_MARKET_DASHBOARD pipeline.

# Purpose
# -------
# Calculate a numerical Strength Score for every instrument, using:

#     - 1Y / 3Y / 5Y performance (from the downloader summary DataFrames)
#     - SMA20 / SMA100 / SMA200 relationship (price above/below each SMA)
#     - RSI14 positioning
#     - MACD histogram direction/magnitude
#     - Bollinger Band position

# Instruments are then ranked SEPARATELY within their own category
# (Nifty / Global / Assets). Categories are never mixed into one ranking.

# This module does NOT download any data itself. It receives the DataFrames
# already produced by:
#     - downloaders/market_indices.py, downloaders/global_markets.py,
#       downloaders/assets.py            (Name, Ticker, CurrentPrice,
#                                          Change1D..Change5Y, MarketDate)
#     - calculations/technical_indicators.py (Name, Ticker, Category,
#                                          SMA20/100/200, RSI14, MACD family,
#                                          Bollinger Bands, MarketDate)

# and joins them on Name + Ticker.

# This file must NOT:
#     - download data
#     - write to SQL Server
#     - calculate Market Sentiment
#     - mix Nifty, Global, and Assets into a single ranking

# Scoring notes
# -------------
# StrengthScore is a RELATIVE composite number used to rank instruments
# within their own category - it is not a normalized 0-100 index, since it
# blends raw percentage returns with 0-100-scaled technical sub-scores.
# The weighting below is a reasonable starting point and is intentionally
# kept simple and easy to re-tune later:

#     35% Momentum   (blend of Change1Y / Change3Y / Change5Y)
#     20% Trend      (price vs SMA20 / SMA100 / SMA200, scaled 0-100)
#     20% RSI        (RSI14, already 0-100)
#     15% MACD       (MACD histogram direction/magnitude, scaled 0-100)
#     10% Bollinger  (position within the Bollinger Band range, 0-100)

# Any missing technical component is treated as neutral (50) rather than
# penalizing the instrument for a temporary data gap. Missing return
# components are treated as 0 (no contribution) rather than fabricated.

# Run directly to test:
#     python -m calculations.strength_score
# """
# from __future__ import annotations

# from typing import Optional

# import pandas as pd

# from utils.helpers import setup_logging, safe_float

# logger = setup_logging()

# OUTPUT_COLUMNS = [
#     "Ticker",
#     "Name",
#     "Category",
#     "StrengthScore",
#     "RankWithinCategory",
#     "Signal",
#     "MarketDate",
# ]

# # Component weights (must sum to 1.0).
# WEIGHT_MOMENTUM = 0.35
# WEIGHT_TREND = 0.20
# WEIGHT_RSI = 0.20
# WEIGHT_MACD = 0.15
# WEIGHT_BOLLINGER = 0.10

# # Signal thresholds applied to the final StrengthScore.
# SIGNAL_THRESHOLDS = [
#     (75, "Strong Buy"),
#     (60, "Buy"),
#     (40, "Neutral"),
#     (25, "Sell"),
# ]
# SIGNAL_FLOOR = "Strong Sell"


# # ==========================================================================
# # COMPONENT SCORES
# # ==========================================================================
# def _momentum_component(change_1y, change_3y, change_5y) -> float:
#     """
#     Blend 1Y/3Y/5Y returns into one momentum figure, annualizing the
#     longer periods so they are comparable to Change1Y. Missing periods
#     contribute 0 rather than being fabricated.
#     """
#     one_year = safe_float(change_1y) or 0.0
#     three_year_annualized = (safe_float(change_3y) or 0.0) / 3.0
#     five_year_annualized = (safe_float(change_5y) or 0.0) / 5.0
#     return (0.5 * one_year) + (0.3 * three_year_annualized) + (0.2 * five_year_annualized)


# def _trend_component(current_price, sma20, sma100, sma200) -> float:
#     """
#     Scores 0-100 based on how many available SMAs the current price is
#     trading above. Returns neutral 50 if no SMA is available at all.
#     """
#     price = safe_float(current_price)
#     if price is None:
#         return 50.0

#     checks = []
#     for sma in (sma20, sma100, sma200):
#         value = safe_float(sma)
#         if value is not None and value != 0:
#             checks.append(price > value)

#     if not checks:
#         return 50.0
#     return (sum(checks) / len(checks)) * 100.0


# def _rsi_component(rsi14) -> float:
#     """RSI is already a 0-100 scale; missing data defaults to neutral 50."""
#     value = safe_float(rsi14)
#     return value if value is not None else 50.0


# def _macd_component(macd_histogram, current_price) -> float:
#     """
#     Scores 0-100 from the MACD histogram's sign and magnitude relative to
#     price. Centered at 50 (no momentum); scaled so a histogram worth
#     roughly 1% of price maps to a fairly strong reading.
#     """
#     histogram = safe_float(macd_histogram)
#     price = safe_float(current_price)
#     if histogram is None or price is None or price == 0:
#         return 50.0

#     pct_of_price = (histogram / price) * 100.0
#     scaled = 50.0 + (pct_of_price * 50.0)
#     return max(0.0, min(100.0, scaled))


# def _bollinger_component(current_price, lower, upper) -> float:
#     """
#     Scores 0-100 based on where the current price sits between the
#     Bollinger lower and upper bands (0 = at/below lower band, 100 = at/
#     above upper band). Neutral 50 if bands are unavailable or degenerate.
#     """
#     price = safe_float(current_price)
#     low = safe_float(lower)
#     high = safe_float(upper)
#     if price is None or low is None or high is None or high <= low:
#         return 50.0

#     position = ((price - low) / (high - low)) * 100.0
#     return max(0.0, min(100.0, position))


# def _signal_from_score(score: float) -> str:
#     for threshold, label in SIGNAL_THRESHOLDS:
#         if score >= threshold:
#             return label
#     return SIGNAL_FLOOR


# # ==========================================================================
# # MAIN CALCULATION
# # ==========================================================================
# def calculate_strength_scores(
#     performance_df: pd.DataFrame,
#     technical_df: pd.DataFrame,
#     category: str,
# ) -> pd.DataFrame:
#     """
#     Calculate StrengthScore and RankWithinCategory for a single category.

#     Parameters
#     ----------
#     performance_df : DataFrame from a downloader (Name, Ticker,
#         CurrentPrice, Change1D..Change5Y, MarketDate).
#     technical_df : DataFrame from calculations.technical_indicators,
#         already filtered or tagged to this same category.
#     category : "Nifty", "Global", or "Assets" - stored in the output and
#         used to keep rankings separate.

#     Instruments present in performance_df but missing from technical_df
#     are skipped (logged), since a trend/RSI/MACD/Bollinger reading is
#     required to compute a meaningful score.
#     """
#     if performance_df is None or performance_df.empty:
#         logger.warning("strength_score (%s): empty performance data.", category)
#         return pd.DataFrame(columns=OUTPUT_COLUMNS)
#     if technical_df is None or technical_df.empty:
#         logger.warning("strength_score (%s): empty technical indicator data.", category)
#         return pd.DataFrame(columns=OUTPUT_COLUMNS)
#     # Ensure technical_df has a 'Name' column if that's what performance_df uses
#     if 'Name' not in technical_df.columns and 'Symbol' in technical_df.columns:
#         technical_df = technical_df.rename(columns={'Symbol': 'Name'})

#     # merged = performance_df.merge(
#     #     technical_df,
#     #     on=["Name", "Date"],
#     #     how="inner",
#     #     suffixes=("", "_tech"),
#     # )
#     merged = performance_df.merge(
#         technical_df,
#         on=["Name", "Ticker"],
#         how="inner",
#         suffixes=("", "_tech"),
#     )

#     missing = set(performance_df["Ticker"]) - set(merged["Ticker"])
#     if missing:
#         logger.warning(
#             "strength_score (%s): %d instrument(s) skipped - no matching "
#             "technical indicator row: %s",
#             category,
#             len(missing),
#             sorted(missing),
#         )

#     if merged.empty:
#         return pd.DataFrame(columns=OUTPUT_COLUMNS)

#     rows = []
#     for _, instrument in merged.iterrows():
#         momentum = _momentum_component(
#             instrument.get("Change1Y"),
#             instrument.get("Change3Y"),
#             instrument.get("Change5Y"),
#         )
#         trend = _trend_component(
#             instrument.get("CurrentPrice"),
#             instrument.get("SMA20"),
#             instrument.get("SMA100"),
#             instrument.get("SMA200"),
#         )
#         rsi = _rsi_component(instrument.get("RSI14"))
#         macd = _macd_component(
#             instrument.get("MACDHistogram"),
#             instrument.get("CurrentPrice"),
#         )
#         bollinger = _bollinger_component(
#             instrument.get("CurrentPrice"),
#             instrument.get("BollingerLower"),
#             instrument.get("BollingerUpper"),
#         )

#         score = (
#             (WEIGHT_MOMENTUM * momentum)
#             + (WEIGHT_TREND * trend)
#             + (WEIGHT_RSI * rsi)
#             + (WEIGHT_MACD * macd)
#             + (WEIGHT_BOLLINGER * bollinger)
#         )

#         market_date = instrument.get("MarketDate")
#         if pd.isna(market_date):
#             market_date = instrument.get("MarketDate_tech")

#         rows.append(
#             {
#                 "Ticker": instrument["Ticker"],
#                 "Name": instrument["Name"],
#                 "Category": category,
#                 "StrengthScore": round(score, 4),
#                 "MarketDate": market_date,
#             }
#         )

#     result = pd.DataFrame(rows)
#     result = result.sort_values("StrengthScore", ascending=False).reset_index(drop=True)
#     result["RankWithinCategory"] = result.index + 1
#     result["Signal"] = result["StrengthScore"].map(_signal_from_score)
#     result = result[OUTPUT_COLUMNS]

#     logger.info(
#         "strength_score (%s): scored %d/%d instrument(s).",
#         category,
#         len(result),
#         len(performance_df),
#     )
#     return result


# def get_all_strength_scores(
#     market_indices_df: pd.DataFrame,
#     market_indices_technical_df: pd.DataFrame,
#     global_markets_df: pd.DataFrame,
#     global_markets_technical_df: pd.DataFrame,
#     assets_df: pd.DataFrame,
#     assets_technical_df: pd.DataFrame,
# ) -> pd.DataFrame:
#     """
#     Convenience function: calculate Strength Scores for all three
#     categories (each ranked separately) and return one combined
#     DataFrame, sorted by Category then RankWithinCategory.
#     """
#     frames = [
#         calculate_strength_scores(market_indices_df, market_indices_technical_df, "Nifty"),
#         calculate_strength_scores(global_markets_df, global_markets_technical_df, "Global"),
#         calculate_strength_scores(assets_df, assets_technical_df, "Assets"),
#     ]
#     non_empty = [frame for frame in frames if not frame.empty]
#     if not non_empty:
#         return pd.DataFrame(columns=OUTPUT_COLUMNS)
#     return pd.concat(non_empty, ignore_index=True)[OUTPUT_COLUMNS]


# if __name__ == "__main__":
#     # Self-contained pipeline test: pulls real data from the downloaders
#     # and technical_indicators modules so this file can be run on its own.
#     from downloaders.market_indices import fetch_market_indices_data
#     from downloaders.global_markets import get_global_markets_data
#     from downloaders.assets import get_assets_data
#     from calculations.technical_indicators import (
#         get_market_indices_technical_indicators,
#         get_global_markets_technical_indicators,
#         get_assets_technical_indicators,
#     )

#     print("Running strength score calculation test...")

#     market_perf = fetch_market_indices_data()
#     global_perf = get_global_markets_data()
#     assets_perf = get_assets_data()

#     market_tech = get_market_indices_technical_indicators()
#     global_tech = get_global_markets_technical_indicators()
#     assets_tech = get_assets_technical_indicators()

#     df = get_all_strength_scores(
#         market_perf, market_tech,
#         global_perf, global_tech,
#         assets_perf, assets_tech,
#     )

#     if df.empty:
#         print("\nNo strength score data produced.")
#     else:
#         display_df = df.copy()
#         display_df["StrengthScore"] = display_df["StrengthScore"].map(lambda v: f"{v:,.2f}")
#         print("\nFINAL STRENGTH SCORE RESULT:")
#         print(display_df.to_string(index=False))
#         print(f"\nProcessed {len(df)} instrument(s) across all categories.")
"""
calculations/strength_score.py

STEP 8 of the STOCK_MARKET_DASHBOARD pipeline.

Purpose
-------
Calculate a numerical Strength Score for every instrument, using:

    - 1Y / 3Y / 5Y performance (from the downloader summary DataFrames)
    - SMA20 / SMA100 / SMA200 relationship (price above/below each SMA)
    - RSI14 positioning
    - MACD histogram direction/magnitude
    - Bollinger Band position

Instruments are then ranked SEPARATELY within their own category
(Nifty / Global / Assets). Categories are never mixed into one ranking.

This module does NOT download any data itself. It receives the DataFrames
already produced by:
    - downloaders/market_indices.py, downloaders/global_markets.py,
      downloaders/assets.py            (Name, Ticker, CurrentPrice,
                                         Change1D..Change5Y, MarketDate)
    - calculations/technical_indicators.py (Name, Ticker, Category,
                                         SMA20/100/200, RSI14, MACD family,
                                         Bollinger Bands, MarketDate)

and joins them on Name + Ticker.

This file must NOT:
    - download data
    - write to SQL Server
    - calculate Market Sentiment
    - mix Nifty, Global, and Assets into a single ranking

Scoring notes
-------------
StrengthScore is a RELATIVE composite number used to rank instruments
within their own category - it is not a normalized 0-100 index, since it
blends raw percentage returns with 0-100-scaled technical sub-scores.
The weighting below is a reasonable starting point and is intentionally
kept simple and easy to re-tune later:

    35% Momentum   (blend of Change1Y / Change3Y / Change5Y)
    20% Trend      (price vs SMA20 / SMA100 / SMA200, scaled 0-100)
    20% RSI        (RSI14, already 0-100)
    15% MACD       (MACD histogram direction/magnitude, scaled 0-100)
    10% Bollinger  (position within the Bollinger Band range, 0-100)

Any missing technical component is treated as neutral (50) rather than
penalizing the instrument for a temporary data gap. Missing return
components are treated as 0 (no contribution) rather than fabricated.

Run directly to test:
    python -m calculations.strength_score
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from utils.helpers import setup_logging, safe_float

logger = setup_logging()

OUTPUT_COLUMNS = [
    "Ticker",
    "Name",
    "Category",
    "StrengthScore",
    "RankWithinCategory",
    "Signal",
    "MarketDate",
]

# Component weights (must sum to 1.0).
WEIGHT_MOMENTUM = 0.35
WEIGHT_TREND = 0.20
WEIGHT_RSI = 0.20
WEIGHT_MACD = 0.15
WEIGHT_BOLLINGER = 0.10

# Signal thresholds applied to the final StrengthScore.
SIGNAL_THRESHOLDS = [
    (75, "Strong Buy"),
    (60, "Buy"),
    (40, "Neutral"),
    (25, "Sell"),
]
SIGNAL_FLOOR = "Strong Sell"


# ==========================================================================
# COMPONENT SCORES
# ==========================================================================
def _momentum_component(change_1y, change_3y, change_5y) -> float:
    """
    Blend 1Y/3Y/5Y returns into one momentum figure, annualizing the
    longer periods so they are comparable to Change1Y. Missing periods
    contribute 0 rather than being fabricated.
    """
    one_year = safe_float(change_1y) or 0.0
    three_year_annualized = (safe_float(change_3y) or 0.0) / 3.0
    five_year_annualized = (safe_float(change_5y) or 0.0) / 5.0
    return (0.5 * one_year) + (0.3 * three_year_annualized) + (0.2 * five_year_annualized)


def _trend_component(current_price, sma20, sma100, sma200) -> float:
    """
    Scores 0-100 based on how many available SMAs the current price is
    trading above. Returns neutral 50 if no SMA is available at all.
    """
    price = safe_float(current_price)
    if price is None:
        return 50.0

    checks = []
    for sma in (sma20, sma100, sma200):
        value = safe_float(sma)
        if value is not None and value != 0:
            checks.append(price > value)

    if not checks:
        return 50.0
    return (sum(checks) / len(checks)) * 100.0


def _rsi_component(rsi14) -> float:
    """RSI is already a 0-100 scale; missing data defaults to neutral 50."""
    value = safe_float(rsi14)
    return value if value is not None else 50.0


def _macd_component(macd_histogram, current_price) -> float:
    """
    Scores 0-100 from the MACD histogram's sign and magnitude relative to
    price. Centered at 50 (no momentum); scaled so a histogram worth
    roughly 1% of price maps to a fairly strong reading.
    """
    histogram = safe_float(macd_histogram)
    price = safe_float(current_price)
    if histogram is None or price is None or price == 0:
        return 50.0

    pct_of_price = (histogram / price) * 100.0
    scaled = 50.0 + (pct_of_price * 50.0)
    return max(0.0, min(100.0, scaled))


def _bollinger_component(current_price, lower, upper) -> float:
    """
    Scores 0-100 based on where the current price sits between the
    Bollinger lower and upper bands (0 = at/below lower band, 100 = at/
    above upper band). Neutral 50 if bands are unavailable or degenerate.
    """
    price = safe_float(current_price)
    low = safe_float(lower)
    high = safe_float(upper)
    if price is None or low is None or high is None or high <= low:
        return 50.0

    position = ((price - low) / (high - low)) * 100.0
    return max(0.0, min(100.0, position))


def _signal_from_score(score: float) -> str:
    for threshold, label in SIGNAL_THRESHOLDS:
        if score >= threshold:
            return label
    return SIGNAL_FLOOR


# ==========================================================================
# MAIN CALCULATION
# ==========================================================================
def calculate_strength_scores(
    performance_df: pd.DataFrame,
    technical_df: pd.DataFrame,
    category: str,
) -> pd.DataFrame:
    """
    Calculate StrengthScore and RankWithinCategory for a single category.

    Parameters
    ----------
    performance_df : DataFrame from a downloader (Name, Ticker,
        CurrentPrice, Change1D..Change5Y, MarketDate).
    technical_df : DataFrame from calculations.technical_indicators,
        already filtered or tagged to this same category.
    category : "Nifty", "Global", or "Assets" - stored in the output and
        used to keep rankings separate.

    Instruments present in performance_df but missing from technical_df
    are skipped (logged), since a trend/RSI/MACD/Bollinger reading is
    required to compute a meaningful score.
    """
    if performance_df is None or performance_df.empty:
        logger.warning("strength_score (%s): empty performance data.", category)
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    if technical_df is None or technical_df.empty:
        logger.warning("strength_score (%s): empty technical indicator data.", category)
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    # Ensure technical_df has a 'Name' column if that's what performance_df uses
    if 'Name' not in technical_df.columns and 'Symbol' in technical_df.columns:
        technical_df = technical_df.rename(columns={'Symbol': 'Name'})

    # Join on Name + Ticker: both performance_df (downloaders) and
    # technical_df (calculations.technical_indicators) carry these two
    # columns. Neither DataFrame has a 'Date' column, so joining on
    # "Date" (as an earlier version of this file did) always fails with
    # a KeyError.
    merged = performance_df.merge(
        technical_df,
        on=["Name", "Ticker"],
        how="inner",
        suffixes=("", "_tech"),
    )

    missing = set(performance_df["Ticker"]) - set(merged["Ticker"])
    if missing:
        logger.warning(
            "strength_score (%s): %d instrument(s) skipped - no matching "
            "technical indicator row: %s",
            category,
            len(missing),
            sorted(missing),
        )

    if merged.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    rows = []
    for _, instrument in merged.iterrows():
        momentum = _momentum_component(
            instrument.get("Change1Y"),
            instrument.get("Change3Y"),
            instrument.get("Change5Y"),
        )
        trend = _trend_component(
            instrument.get("CurrentPrice"),
            instrument.get("SMA20"),
            instrument.get("SMA100"),
            instrument.get("SMA200"),
        )
        rsi = _rsi_component(instrument.get("RSI14"))
        macd = _macd_component(
            instrument.get("MACDHistogram"),
            instrument.get("CurrentPrice"),
        )
        bollinger = _bollinger_component(
            instrument.get("CurrentPrice"),
            instrument.get("BollingerLower"),
            instrument.get("BollingerUpper"),
        )

        score = (
            (WEIGHT_MOMENTUM * momentum)
            + (WEIGHT_TREND * trend)
            + (WEIGHT_RSI * rsi)
            + (WEIGHT_MACD * macd)
            + (WEIGHT_BOLLINGER * bollinger)
        )

        market_date = instrument.get("MarketDate")
        if pd.isna(market_date):
            market_date = instrument.get("MarketDate_tech")

        rows.append(
            {
                "Ticker": instrument["Ticker"],
                "Name": instrument["Name"],
                "Category": category,
                "StrengthScore": round(score, 4),
                "MarketDate": market_date,
            }
        )

    result = pd.DataFrame(rows)
    result = result.sort_values("StrengthScore", ascending=False).reset_index(drop=True)
    result["RankWithinCategory"] = result.index + 1
    result["Signal"] = result["StrengthScore"].map(_signal_from_score)
    result = result[OUTPUT_COLUMNS]

    logger.info(
        "strength_score (%s): scored %d/%d instrument(s).",
        category,
        len(result),
        len(performance_df),
    )
    return result


def get_all_strength_scores(
    market_indices_df: pd.DataFrame,
    market_indices_technical_df: pd.DataFrame,
    global_markets_df: pd.DataFrame,
    global_markets_technical_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    assets_technical_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convenience function: calculate Strength Scores for all three
    categories (each ranked separately) and return one combined
    DataFrame, sorted by Category then RankWithinCategory.
    """
    frames = [
        calculate_strength_scores(market_indices_df, market_indices_technical_df, "Nifty"),
        calculate_strength_scores(global_markets_df, global_markets_technical_df, "Global"),
        calculate_strength_scores(assets_df, assets_technical_df, "Assets"),
    ]
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return pd.concat(non_empty, ignore_index=True)[OUTPUT_COLUMNS]


if __name__ == "__main__":
    # Self-contained pipeline test: pulls real data from the downloaders
    # and technical_indicators modules so this file can be run on its own.
    from downloaders.market_indices import fetch_market_indices_data
    from downloaders.global_markets import get_global_markets_data
    from downloaders.assets import get_assets_data
    from calculations.technical_indicators import (
        get_market_indices_technical_indicators,
        get_global_markets_technical_indicators,
        get_assets_technical_indicators,
    )

    print("Running strength score calculation test...")

    market_perf = fetch_market_indices_data()
    global_perf = get_global_markets_data()
    assets_perf = get_assets_data()

    market_tech = get_market_indices_technical_indicators()
    global_tech = get_global_markets_technical_indicators()
    assets_tech = get_assets_technical_indicators()

    df = get_all_strength_scores(
        market_perf, market_tech,
        global_perf, global_tech,
        assets_perf, assets_tech,
    )

    if df.empty:
        print("\nNo strength score data produced.")
    else:
        display_df = df.copy()
        display_df["StrengthScore"] = display_df["StrengthScore"].map(lambda v: f"{v:,.2f}")
        print("\nFINAL STRENGTH SCORE RESULT:")
        print(display_df.to_string(index=False))
        print(f"\nProcessed {len(df)} instrument(s) across all categories.")