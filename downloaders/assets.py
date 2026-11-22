"""
downloaders/assets.py

STEP 6 of the STOCK_MARKET_DASHBOARD pipeline.

Purpose
-------
Read the assets sheet from MARKET.xlsx (Gold, Silver, USD/INR, Brent Crude
Oil, Bitcoin, and optionally US Dollar Index) and download historical
data for every ACTIVE instrument using yfinance. Returns a clean
DataFrame ready for the calculation/database layers.

Data source: yfinance ONLY (per the updated project spec, Jugaad Data is
used exclusively for the 8 Nifty market indices, not for Assets).

Architecture:
    MARKET.xlsx (assets sheet)
        -> active instruments (AssetName -> Name, Tickers -> Ticker)
        -> yfinance historical data (utils.helpers.download_ticker_history)
        -> return-period calculations (utils.helpers.compute_return_periods)
        -> clean 12-column DataFrame

This file must NOT:
    - write to SQL Server
    - calculate technical indicators (SMA/RSI/MACD/Bollinger)
    - calculate strength scores or rankings
    - calculate market sentiment
    - insert fake/zero values for instruments that fail to download

Run directly to test:
    python -m downloaders.assets
"""

import pandas as pd

from utils.helpers import (
    setup_logging,
    read_excel_sheet,
    download_ticker_history,
    compute_return_periods,
)

logger = setup_logging()

# Exact 12 columns required by the rest of the pipeline (README section 7).
OUTPUT_COLUMNS = [
    "Name",
    "Ticker",
    "CurrentPrice",
    "Change1D",
    "Change1W",
    "Change1M",
    "Change3M",
    "Change6M",
    "Change1Y",
    "Change3Y",
    "Change5Y",
    "MarketDate",
]


def get_assets_data() -> pd.DataFrame:
    """
    Download current data and return metrics for every active instrument
    in the assets Excel sheet (Gold, Silver, USD/INR, Brent, Bitcoin,
    US Dollar Index if active).

    For each active instrument:
        1. Download ~6 years of daily history from yfinance.
        2. Calculate CurrentPrice, MarketDate, and Change1D..Change5Y.
        3. Skip the instrument (with a logged warning) if either step
           fails - never insert a fake price, fake date, or 0% change.

    Returns
    -------
    pandas.DataFrame with exactly OUTPUT_COLUMNS. May contain fewer rows
    than active instruments if some downloads failed.
    """
    instruments = read_excel_sheet("assets")
    active = instruments[instruments["Active"]].reset_index(drop=True)

    logger.info("assets: %d active instrument(s) to process.", len(active))

    rows = []
    for _, instrument in active.iterrows():
        name = instrument["Name"]
        ticker = instrument["Ticker"]

        logger.info("assets: processing '%s' (%s) via yfinance.", name, ticker)

        history = download_ticker_history(ticker, years=6)
        if history is None:
            logger.warning(
                "assets: skipping '%s' (%s) - no data returned by yfinance.",
                name,
                ticker,
            )
            continue

        metrics = compute_return_periods(history)
        if metrics is None:
            logger.warning(
                "assets: skipping '%s' (%s) - could not calculate current "
                "price/return metrics from the downloaded history.",
                name,
                ticker,
            )
            continue

        row = {"Name": name, "Ticker": ticker}
        row.update(metrics)
        rows.append(row)

    if not rows:
        logger.warning("assets: no instruments produced valid data.")
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    result = pd.DataFrame(rows)
    result = result[OUTPUT_COLUMNS]
    result = result.sort_values("Name").reset_index(drop=True)

    logger.info(
        "assets: finished, %d/%d instrument(s) succeeded.",
        len(result),
        len(active),
    )
    return result


if __name__ == "__main__":
    df = get_assets_data()
    print(df.to_string(index=False))