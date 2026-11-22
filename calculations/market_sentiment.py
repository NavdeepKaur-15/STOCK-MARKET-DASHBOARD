"""
calculations/market_sentiment.py

STEP 9 of the STOCK_MARKET_DASHBOARD pipeline.

Purpose
-------
Calculate Market Sentiment separately for Nifty, Global Markets, and
Assets, using ONLY the Change1D values already calculated by the
downloaders:

    MarketIndices.Change1D  -> Nifty sentiment
    GlobalMarkets.Change1D  -> Global sentiment
    Assets.Change1D         -> Assets sentiment

Classification rule (per completed trading day):
    Change1D > 0  -> Bullish / Green
    Change1D < 0  -> Bearish / Red
    Change1D == 0 -> Neutral

Because the classification rule is identical for both the Bullish/
Neutral/Bearish counts and the Green/Neutral/Red counts required by the
project spec, those two sets of fields intentionally mirror each other
(GreenCount == BullishCount, RedCount == BearishCount,
NeutralChangeCount == NeutralCount). Both are still produced separately
below to match the required SQL schema exactly.

This module does NOT:
    - download any market data itself
    - use RSI, MACD, StrengthScore, or any other indicator
    - use the currently active/incomplete trading session
      (Change1D from the downloaders is already based on the last
      completed session - see utils.helpers.last_completed_trading_date)
    - mix Nifty, Global, and Assets together

Run directly to test:
    python -m calculations.market_sentiment
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from utils.helpers import setup_logging, safe_float

logger = setup_logging()

OUTPUT_COLUMNS = [
    "Category",
    "BullishCount",
    "NeutralCount",
    "BearishCount",
    "TotalCount",
    "BullishPercentage",
    "NeutralPercentage",
    "BearishPercentage",
    "GreenCount",
    "RedCount",
    "NeutralChangeCount",
    "GreenPercentage",
    "RedPercentage",
    "NeutralChangePercentage",
    "OverallSentiment",
    "MarketDate",
]

# OverallSentiment thresholds, applied to BullishPercentage/BearishPercentage.
STRONG_THRESHOLD = 65.0


def _pct(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100.0, 2)


def _overall_sentiment(bullish_pct: float, bearish_pct: float) -> str:
    if bullish_pct >= STRONG_THRESHOLD:
        return "Strongly Bullish"
    if bearish_pct >= STRONG_THRESHOLD:
        return "Strongly Bearish"
    if bullish_pct > bearish_pct:
        return "Bullish"
    if bearish_pct > bullish_pct:
        return "Bearish"
    return "Neutral"


def _most_common_market_date(series: pd.Series):
    """
    The MarketDate should already be identical (or very nearly so) across
    every instrument in a category, since they all come from the same
    "last completed trading day" logic. If a category ever has more than
    one distinct MarketDate (e.g. one instrument's download lagged
    behind), use the most frequently occurring date and log a warning
    rather than silently guessing.
    """
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    counts = cleaned.value_counts()
    if len(counts) > 1:
        logger.warning(
            "market_sentiment: multiple distinct MarketDate values found "
            "(%s) - using the most common one.",
            dict(counts),
        )
    return counts.index[0]


def calculate_sentiment_for_category(df: pd.DataFrame, category: str) -> Optional[dict]:
    """
    Calculate the full sentiment record for one category's DataFrame.

    Parameters
    ----------
    df : DataFrame from a downloader (must contain Change1D and
        MarketDate). Category-specific - never mix categories here.
    category : "Nifty", "Global", or "Assets".

    Returns None if the DataFrame is empty or has no usable Change1D
    values (never fabricates a sentiment reading from missing data).
    """
    if df is None or df.empty:
        logger.warning("market_sentiment (%s): no data to evaluate.", category)
        return None
    if "Change1D" not in df.columns:
        logger.warning("market_sentiment (%s): Change1D column missing.", category)
        return None

    changes = df["Change1D"].map(safe_float).dropna()
    if changes.empty:
        logger.warning("market_sentiment (%s): no usable Change1D values.", category)
        return None

    bullish_count = int((changes > 0).sum())
    bearish_count = int((changes < 0).sum())
    neutral_count = int((changes == 0).sum())
    total_count = bullish_count + bearish_count + neutral_count

    bullish_pct = _pct(bullish_count, total_count)
    bearish_pct = _pct(bearish_count, total_count)
    neutral_pct = _pct(neutral_count, total_count)

    market_date = _most_common_market_date(df["MarketDate"]) if "MarketDate" in df.columns else None

    record = {
        "Category": category,
        "BullishCount": bullish_count,
        "NeutralCount": neutral_count,
        "BearishCount": bearish_count,
        "TotalCount": total_count,
        "BullishPercentage": bullish_pct,
        "NeutralPercentage": neutral_pct,
        "BearishPercentage": bearish_pct,
        # Green/Red/NeutralChange mirror Bullish/Bearish/Neutral exactly,
        # since both use the same Change1D > 0 / < 0 / == 0 rule.
        "GreenCount": bullish_count,
        "RedCount": bearish_count,
        "NeutralChangeCount": neutral_count,
        "GreenPercentage": bullish_pct,
        "RedPercentage": bearish_pct,
        "NeutralChangePercentage": neutral_pct,
        "OverallSentiment": _overall_sentiment(bullish_pct, bearish_pct),
        "MarketDate": market_date,
    }

    logger.info(
        "market_sentiment (%s): %d bullish / %d neutral / %d bearish "
        "(%d total) -> %s.",
        category,
        bullish_count,
        neutral_count,
        bearish_count,
        total_count,
        record["OverallSentiment"],
    )
    return record


def get_market_sentiment(
    market_indices_df: pd.DataFrame,
    global_markets_df: pd.DataFrame,
    assets_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate Market Sentiment separately for Nifty, Global, and Assets
    and return one row per category.
    """
    records = []
    for df, category in (
        (market_indices_df, "Nifty"),
        (global_markets_df, "Global"),
        (assets_df, "Assets"),
    ):
        record = calculate_sentiment_for_category(df, category)
        if record is not None:
            records.append(record)

    if not records:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    result = pd.DataFrame(records)
    return result[OUTPUT_COLUMNS]


if __name__ == "__main__":
    # Self-contained pipeline test: pulls real data from the downloaders
    # so this file can be run on its own.
    from downloaders.market_indices import fetch_market_indices_data
    from downloaders.global_markets import get_global_markets_data
    from downloaders.assets import get_assets_data

    print("Running market sentiment calculation test...")

    market_df = fetch_market_indices_data()
    global_df = get_global_markets_data()
    assets_df = get_assets_data()

    df = get_market_sentiment(market_df, global_df, assets_df)

    if df.empty:
        print("\nNo market sentiment data produced.")
    else:
        print("\nFINAL MARKET SENTIMENT RESULT:")
        print(df.to_string(index=False))