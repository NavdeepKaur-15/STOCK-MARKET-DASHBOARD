from datetime import date, timedelta
import os
import pandas as pd
from dateutil.relativedelta import relativedelta
from jugaad_data.nse import index_raw
INDICES = [
    {"Name": "Nifty 50", "Ticker": "^NSEI", "JugaadName": "NIFTY 50"},
    {"Name": "Nifty 100", "Ticker": "^CNX100", "JugaadName": "NIFTY 100"},
    {"Name": "Nifty 500", "Ticker": "^CRSLDX", "JugaadName": "NIFTY 500"},
    {"Name": "Nifty Midcap 50", "Ticker": "^NSEMDCP50", "JugaadName": "NIFTY MIDCAP 50"},
    {"Name": "Nifty Midcap 150", "Ticker": "NIFTYMIDCAP150.NS", "JugaadName": "NIFTY MIDCAP 150"},
    {"Name": "Nifty Smallcap 100", "Ticker": "^CNXSC", "JugaadName": "NIFTY SMALLCAP 100"},
    {"Name": "Nifty Smallcap 250", "Ticker": "NIFTYSMLCAP250.NS", "JugaadName": "NIFTY SMALLCAP 250"},
    {"Name": "Nifty Microcap 250", "Ticker": "NIFTY_MICROCAP250.NS", "JugaadName": "NIFTY MICROCAP 250"},
]
CACHE_DIR = os.path.join(os.getcwd(), ".jugaad_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
os.environ["J_CACHE_DIR"] = CACHE_DIR
def clean_history(raw):
    df = pd.DataFrame(raw)
    if df.empty:
        raise ValueError("Historical data is empty")
    date_col = next(
        (
            c for c in df.columns
            if str(c).strip().lower() in {
                "historicaldate",
                "historical date",
                "date",
            }
        ),
        None,
    )
    close_col = next(
        (
            c for c in df.columns
            if str(c).strip().lower() in {
                "close",
                "closing value",
                "closing index value",
            }
        ),
        None,
    )
    if date_col is None:
        raise ValueError(
            f"Date column not found: {list(df.columns)}"
        )
    if close_col is None:
        raise ValueError(
            f"CLOSE column not found: {list(df.columns)}"
        )
    result = df[[date_col, close_col]].copy()
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
        raise ValueError("No valid historical rows")
    return result
def get_trading_session_on_or_before(history, target_date):
    """
    Find the NSE trading session on target_date.
    If target_date was a weekend or NSE holiday,
    use the most recent completed trading session
    before that date.
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
    Calculate the exact calendar target date for
    each rolling period.
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
def process_index(index_info, from_date, to_date):
    name = index_info["Name"]
    ticker = index_info["Ticker"]
    jugaad_name = index_info["JugaadName"]
    print(
        f"Processing {name}...",
        end=" ",
    )
    raw = index_raw(
        jugaad_name,
        from_date,
        to_date,
    )
    history = clean_history(raw)
    # Latest completed NSE trading session.
    market_date = history["Date"].iloc[-1].date()
    current_price = float(
        history["Close"].iloc[-1]
    )
    # Calculate exact calendar dates first.
    target_dates = get_period_dates(
        market_date
    )
    results = {
        "Name": name,
        "Ticker": ticker,
        "CurrentPrice": current_price,
    }
    audit = {
        "Name": name,
        "CurrentDate": market_date,
        "CurrentPrice": current_price,
    }
    for period, target_date in target_dates.items():
        actual_date, previous_price = (
            get_trading_session_on_or_before(
                history,
                target_date,
            )
        )
        return_pct = calculate_return(
            current_price,
            previous_price,
        )
        results[f"Change%{period}"] = return_pct
        audit[f"{period}TargetDate"] = target_date
        audit[f"{period}TradingDate"] = actual_date
        audit[f"{period}StartPrice"] = previous_price
    results["MarketDate"] = market_date
    print("OK")
    return results, audit
def main():
    print("NIFTY 8-INDEX FINAL ROLLING RETURN TEST")
    print("-" * 100)
    today = date.today()
    # Five years plus extra history so that the exact
    # 5-year target date is always available.
    from_date = date(
        today.year - 6,
        1,
        1,
    )
    to_date = today
    print(
        f"Historical data: {from_date} -> {to_date}"
    )
    results = []
    audits = []
    for index_info in INDICES:
        try:
            result, audit = process_index(
                index_info,
                from_date,
                to_date,
            )
            results.append(result)
            audits.append(audit)
        except Exception as e:
            print(
                f"FAIL: {e}"
            )
    if not results:
        print("No data returned.")
        return
    # ---------------------------------------------------------
    # FINAL PERCENTAGE TABLE
    # ---------------------------------------------------------
    columns = [
        "Name",
        "Ticker",
        "CurrentPrice",
        "Change%1D",
        "Change%1W",
        "Change%1M",
        "Change%3M",
        "Change%6M",
        "Change%1Y",
        "Change%3Y",
        "Change%5Y",
        "MarketDate",
    ]
    df = pd.DataFrame(
        results,
        columns=columns,
    )
    display_df = df.copy()
    display_df["CurrentPrice"] = (
        display_df["CurrentPrice"].map(
            lambda x:
                f"{x:,.2f}"
                if pd.notna(x)
                else "-"
        )
    )
    percentage_columns = [
        "Change%1D",
        "Change%1W",
        "Change%1M",
        "Change%3M",
        "Change%6M",
        "Change%1Y",
        "Change%3Y",
        "Change%5Y",
    ]
    for column in percentage_columns:
        display_df[column] = (
            display_df[column].map(
                lambda x:
                    f"{x:+.2f}%"
                    if pd.notna(x)
                    else "-"
            )
        )
    print("\nFINAL RESULT")
    print("-" * 100)
    print(
        display_df.to_string(
            index=False
        )
    )
    # ---------------------------------------------------------
    # AUDIT TABLE
    # ---------------------------------------------------------
    audit_df = pd.DataFrame(audits)
    audit_columns = [
        "Name",
        "CurrentDate",
        "CurrentPrice",
        "1DTargetDate",
        "1DTradingDate",
        "1DStartPrice",
        "1WTargetDate",
        "1WTradingDate",
        "1WStartPrice",
        "1MTargetDate",
        "1MTradingDate",
        "1MStartPrice",
        "3MTargetDate",
        "3MTradingDate",
        "3MStartPrice",
        "6MTargetDate",
        "6MTradingDate",
        "6MStartPrice",
        "1YTargetDate",
        "1YTradingDate",
        "1YStartPrice",
        "3YTargetDate",
        "3YTradingDate",
        "3YStartPrice",
        "5YTargetDate",
        "5YTradingDate",
        "5YStartPrice",
    ]
    audit_df = audit_df[
        [
            c for c in audit_columns
            if c in audit_df.columns
        ]
    ]
    print("\nDATE / PRICE AUDIT")
    print("-" * 100)
    print(
        audit_df.to_string(
            index=False
        )
    )
    # ---------------------------------------------------------
    # SAVE BOTH FILES
    # ---------------------------------------------------------
    result_file = (
        "test_nifty_indices_output.csv"
    )
    audit_file = (
        "test_nifty_indices_audit.csv"
    )
    df.to_csv(
        result_file,
        index=False,
    )
    audit_df.to_csv(
        audit_file,
        index=False,
    )
    print(
        f"\nProcessed {len(results)}/8 indices."
    )
    print(
        f"Saved: {result_file}"
    )
    print(
        f"Saved: {audit_file}"
    )
if __name__ == "__main__":
    main()