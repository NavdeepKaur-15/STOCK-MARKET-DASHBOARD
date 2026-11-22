"""
main.py

STEP 11 of the STOCK_MARKET_DASHBOARD pipeline - the orchestrator.

This is the only file you need to run:

    python main.py

It calls every module in the fixed order established for this project
and does nothing else - no downloading, no calculating, no SQL logic of
its own. Each stage below is delegated to the module that owns it:

    MARKET.xlsx
        |
        v
    Download Nifty (Jugaad)      -> downloaders.market_indices
    Download Global Markets (yf) -> downloaders.global_markets
    Download Assets (yf)         -> downloaders.assets
        |
        v
    Calculate technical indicators -> calculations.technical_indicators
    Calculate strength scores      -> calculations.strength_score
    Calculate market sentiment     -> calculations.market_sentiment
        |
        v
    Update SQL (delete old, insert new, commit/rollback)
                                    -> database.update_database

This file must NOT:
    - read Excel directly
    - call yfinance/Jugaad directly
    - calculate indicators, strength scores, or sentiment itself
    - build/write SQL statements itself
    - contain any GUI/web/Power BI logic
"""
from __future__ import annotations

import logging
import time

import pandas as pd

from config.config import CONFIG
from utils.helpers import setup_logging

from downloaders.market_indices import fetch_market_indices_data
from downloaders.global_markets import get_global_markets_data
from downloaders.assets import get_assets_data

from calculations.technical_indicators import (
    get_market_indices_technical_indicators,
    get_global_markets_technical_indicators,
    get_assets_technical_indicators,
)
from calculations.strength_score import get_all_strength_scores
from calculations.market_sentiment import get_market_sentiment

from database.update_database import update_all_tables

logger = setup_logging()


def _combine_technical_frames(*frames: pd.DataFrame) -> pd.DataFrame:
    """Concatenate the per-category technical-indicator DataFrames,
    skipping empty ones. Returns an empty DataFrame (with the same
    columns as the first frame) if every category failed."""
    non_empty = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty:
        return frames[0] if frames else pd.DataFrame()
    return pd.concat(non_empty, ignore_index=True)


def run_pipeline() -> bool:
    """
    Run the full refresh pipeline once, start to finish.
    Returns True if the SQL update committed successfully, False otherwise.
    """
    CONFIG.ensure_directories()
    started_at = time.monotonic()
    logger.info("=" * 70)
    logger.info("STOCK_MARKET_DASHBOARD refresh started.")
    logger.info("Excel source: %s", CONFIG.EXCEL_PATH)
    logger.info("SQL target  : %s / %s", CONFIG.SQL_SERVER, CONFIG.SQL_DATABASE)
    logger.info("=" * 70)

    # ----------------------------------------------------------------
    # 1. Download current + historical data for all three categories.
    #    Excel is read fresh inside each of these calls (README section 8:
    #    Python reads the workbook every refresh, SQL is never the
    #    ticker source).
    # ----------------------------------------------------------------
    logger.info("Step 1/4: downloading market data...")
    market_indices_df = fetch_market_indices_data()
    global_markets_df = get_global_markets_data()
    assets_df = get_assets_data()

    logger.info(
        "Downloaded: %d Nifty indices, %d global markets, %d assets.",
        len(market_indices_df), len(global_markets_df), len(assets_df),
    )

    # ----------------------------------------------------------------
    # 2. Technical indicators (each category calculated separately;
    #    this module downloads its own historical price series - see
    #    calculations/technical_indicators.py).
    # ----------------------------------------------------------------
    logger.info("Step 2/4: calculating technical indicators...")
    market_tech_df = get_market_indices_technical_indicators()
    global_tech_df = get_global_markets_technical_indicators()
    assets_tech_df = get_assets_technical_indicators()
    technical_indicators_df = _combine_technical_frames(
        market_tech_df, global_tech_df, assets_tech_df
    )
    logger.info(
        "Technical indicators calculated for %d instrument(s) total.",
        len(technical_indicators_df),
    )

    # ----------------------------------------------------------------
    # 3. Strength scores (ranked separately per category) and market
    #    sentiment (based only on Change1D from the previous completed
    #    trading day - never mixed across categories).
    # ----------------------------------------------------------------
    logger.info("Step 3/4: calculating strength scores and market sentiment...")
    strength_scores_df = get_all_strength_scores(
        market_indices_df, market_tech_df,
        global_markets_df, global_tech_df,
        assets_df, assets_tech_df,
    )
    market_sentiment_df = get_market_sentiment(
        market_indices_df, global_markets_df, assets_df
    )
    logger.info(
        "Strength scores: %d row(s). Market sentiment: %d category row(s).",
        len(strength_scores_df), len(market_sentiment_df),
    )

    # ----------------------------------------------------------------
    # 4. Write the final snapshot to SQL Server (single transaction:
    #    delete old rows, insert new rows, commit; rollback on failure).
    # ----------------------------------------------------------------
    logger.info("Step 4/4: updating SQL Server...")
    success = update_all_tables(
        market_indices_df,
        global_markets_df,
        assets_df,
        technical_indicators_df,
        strength_scores_df,
        market_sentiment_df,
    )

    elapsed = time.monotonic() - started_at
    logger.info("=" * 70)
    if success:
        logger.info("STOCK_MARKET_DASHBOARD refresh COMPLETED in %.1fs.", elapsed)
    else:
        logger.error(
            "STOCK_MARKET_DASHBOARD refresh FAILED in %.1fs "
            "- SQL was rolled back, previous snapshot is unchanged.",
            elapsed,
        )
    logger.info("=" * 70)
    return success


if __name__ == "__main__":
    ok = run_pipeline()
    print("Refresh completed successfully." if ok else "Refresh FAILED - see logs/dashboard.log for details.")
    raise SystemExit(0 if ok else 1)