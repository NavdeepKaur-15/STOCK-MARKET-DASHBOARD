"""
downloaders/market_indices.py
Downloads the 8 main Nifty market indices using Jugaad Data.
This module:
    - Reads the market_indices sheet from MARKET.xlsx.
    - Uses Jugaad Data for historical NSE index data.
    - Calculates CurrentPrice and rolling returns.
    - Returns one clean DataFrame for the database/calculation layer.
Required output columns:
    Name
    Ticker
    CurrentPrice
    Change1D
    Change1W
    Change1M
    Change3M
    Change6M
    Change1Y
    Change3Y
    Change5Y
    MarketDate
This module does NOT:
    - create SQL tables
    - insert data into SQL
    - delete SQL rows
    - calculate sentiment
    - calculate strength scores
    - create Power BI files
"""
from __future__ import annotations
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
from jugaad_data.nse import index_raw
from utils.helpers import read_excel_sheet, setup_logging
logger = setup_logging()
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
JUGAAD_INDEX_NAMES = {
    "Nifty 50": "NIFTY 50",
    "Nifty 100": "NIFTY 100",
    "Nifty 500": "NIFTY 500",
    "Nifty Midcap 50": "NIFTY MIDCAP 50",
    "Nifty Midcap 150": "NIFTY MIDCAP 150",
    "Nifty Smallcap 100": "NIFTY SMALLCAP 100",
    "Nifty Smallcap 250": "NIFTY SMALLCAP 250",
    "Nifty Microcap 250": "NIFTY MICROCAP 250",
}
def clean_history(raw_data):
    """
    Convert Jugaad historical index data into:
        Date
        Close
    Jugaad versions may return slightly different column names,
    so the function checks several possible names.
    """
    df = pd.DataFrame(raw_data)
    if df.empty:
        raise ValueError("Historical data is empty.")
    date_column = None
    close_column = None
    possible_date_columns = {
        "historicaldate",
        "historical date",
        "date",
    }
    possible_close_columns = {
        "close",
        "closing value",
        "closing index value",
    }
    for column in df.columns:
        normalized = str(column).strip().lower()
        if normalized in possible_date_columns:
            date_column = column
        if normalized in possible_close_columns:
            close_column = column
    if date_column is None:
        raise ValueError(
            f"Date column not found. Columns returned: {list(df.columns)}"
        )
    if close_column is None:
        raise ValueError(
            f"CLOSE column not found. Columns returned: {list(df.columns)}"
        )
    result = df[[date_column, close_column]].copy()
    result.columns = ["Date", "Close"]
    result["Date"] = pd.to_datetime(
        result["Date"],
        errors="coerce",
    )
    result["Close"] = pd.to_numeric(
        result["Close"],
        errors="coerce",
    )
    result = (
        result
        .dropna(subset=["Date", "Close"])
        .sort_values("Date")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )
    if result.empty:
        raise ValueError("No valid historical rows after cleaning.")
    return result
def get_trading_session_on_or_before(history, target_date):
    """
    Find the latest available NSE trading session on or before
    the requested calendar date.
    This handles:
        - weekends
        - NSE holidays
        - other non-trading days
    Example:
        If the exact 1-month date was a Sunday, the function
        uses the previous available NSE trading session.
    """
    target = pd.Timestamp(target_date)
    rows = history[
        history["Date"] <= target
    ]
    if rows.empty:
        return None, None
    row = rows.iloc[-1]
    return (
        row["Date"].date(),
        float(row["Close"]),
    )
def calculate_return(current_price, previous_price):
    """
    Calculate percentage change.
    """
    if (
        current_price is None
        or previous_price is None
        or previous_price == 0
    ):
        return None
    return (
        (current_price / previous_price) - 1
    ) * 100
def get_period_dates(market_date):
    """
    Calculate the exact calendar target date for each
    required rolling period.
    """
    return {
        "1D": market_date - timedelta(days=1),
        "1W": market_date - timedelta(weeks=1),
        "1M": market_date - relativedelta(months=1),
        "3M": market_date - relativedelta(months=3),
        "6M": market_date - relativedelta(months=6),
        "1Y": market_date - relativedelta(years=1),
        "3Y": market_date - relativedelta(years=3),
        "5Y": market_date - relativedelta(years=5),
    }
def download_jugaad_history(jugaad_name, from_date, to_date):
    """
    Download historical data directly using Jugaad's module-level
    index_raw() function.
    We intentionally use index_raw() instead of:
        NSEIndexHistory().index_df()
    because index_df() is a module-level function in the installed
    Jugaad version.
    """
    logger.info(
        "Jugaad: downloading '%s' from %s to %s.",
        jugaad_name,
        from_date,
        to_date,
    )
    raw_data = index_raw(
        jugaad_name,
        from_date,
        to_date,
    )
    history = clean_history(raw_data)
    logger.info(
        "Jugaad: '%s' returned %d usable rows. Oldest=%s, Latest=%s.",
        jugaad_name,
        len(history),
        history["Date"].min().date(),
        history["Date"].max().date(),
    )
    return history
def process_index(index_info, from_date, to_date):
    """
    Download and calculate all required metrics for one index.
    """
    name = index_info["Name"]
    ticker = index_info["Ticker"]
    jugaad_name = JUGAAD_INDEX_NAMES.get(name)
    if not jugaad_name:
        raise ValueError(
            f"No Jugaad index mapping found for '{name}'."
        )
    logger.info(
        "Processing market index: '%s' (Ticker: %s).",
        name,
        ticker,
    )
    history = download_jugaad_history(
        jugaad_name,
        from_date,
        to_date,
    )
    if history.empty:
        raise ValueError(
            f"No historical data returned for '{name}'."
        )
    latest_row = history.iloc[-1]
    market_date = latest_row["Date"].date()
    current_price = float(
        latest_row["Close"]
    )
    target_dates = get_period_dates(
        market_date
    )
    result = {
        "Name": name,
        "Ticker": ticker,
        "CurrentPrice": current_price,
    }
    for period, target_date in target_dates.items():
        _, previous_price = get_trading_session_on_or_before(
            history,
            target_date,
        )
        result[f"Change{period}"] = calculate_return(
            current_price,
            previous_price,
        )
    result["MarketDate"] = market_date
    return result
def fetch_market_indices_data():
    """
    Main downloader function.
    Reads the active market indices from Excel, downloads their
    historical Jugaad data, calculates all required periods, and
    returns a clean DataFrame.
    """
    try:
        sheet = read_excel_sheet("market_indices")
    except Exception as exc:
        logger.error(
            "fetch_market_indices_data(): failed to read Excel sheet: %s",
            exc,
        )
        return pd.DataFrame(
            columns=OUTPUT_COLUMNS
        )
    if sheet.empty:
        logger.warning(
            "fetch_market_indices_data(): market_indices sheet is empty."
        )
        return pd.DataFrame(
            columns=OUTPUT_COLUMNS
        )
    if "Active" in sheet.columns:
        active_indices = sheet[
            sheet["Active"].astype(bool)
        ].copy()
    else:
        active_indices = sheet.copy()
    if active_indices.empty:
        logger.warning(
            "fetch_market_indices_data(): no active market indices found."
        )
        return pd.DataFrame(
            columns=OUTPUT_COLUMNS
        )
    today = date.today()
    # Six calendar years gives us more than enough history
    # for the required 5-year return.
    from_date = date(
        today.year - 6,
        1,
        1,
    )
    to_date = today
    results = []
    for _, index_info in active_indices.iterrows():
        name = index_info["Name"]
        ticker = index_info["Ticker"]
        try:
            result = process_index(
                {
                    "Name": name,
                    "Ticker": ticker,
                },
                from_date,
                to_date,
            )
            results.append(result)
            logger.info(
                "Successfully processed '%s'. MarketDate=%s.",
                name,
                result["MarketDate"],
            )
        except Exception as exc:
            logger.error(
                "Skipping '%s': %s",
                name,
                exc,
            )
    if not results:
        logger.error(
            "fetch_market_indices_data(): no market indices were processed successfully."
        )
        return pd.DataFrame(
            columns=OUTPUT_COLUMNS
        )
    result_df = pd.DataFrame(
        results,
        columns=OUTPUT_COLUMNS,
    )
    return result_df
if __name__ == "__main__":
    print("Running market indices downloader test...")
    df = fetch_market_indices_data()
    if df.empty:
        print("\nNo market index data returned.")
    else:
        display_df = df.copy()
        display_df["CurrentPrice"] = display_df[
            "CurrentPrice"
        ].map(
            lambda value:
            f"{value:,.2f}"
            if pd.notna(value)
            else "-"
        )
        percentage_columns = [
            "Change1D",
            "Change1W",
            "Change1M",
            "Change3M",
            "Change6M",
            "Change1Y",
            "Change3Y",
            "Change5Y",
        ]
        for column in percentage_columns:
            display_df[column] = display_df[
                column
            ].map(
                lambda value:
                f"{value:+.2f}%"
                if pd.notna(value)
                else "-"
            )
        print("\nFINAL MARKET INDICES RESULT:")
        print(
            display_df.to_string(
                index=False
            )
        )
        print(
            f"\nProcessed {len(df)}/8 market indices."
        )