"""
database/update_database.py
STEP 10 of the STOCK_MARKET_DASHBOARD pipeline.
Purpose
-------
Write the final calculated DataFrames into SQL Server.
For every refresh:
    BEGIN TRANSACTION
    Delete old MarketIndices        -> Insert new MarketIndices
    Delete old GlobalMarkets        -> Insert new GlobalMarkets
    Delete old Assets               -> Insert new Assets
    Delete old TechnicalIndicators  -> Insert new TechnicalIndicators
    Delete old StrengthScores       -> Insert new StrengthScores
    Delete old MarketSentiment      -> Insert new MarketSentiment
    COMMIT
If anything fails:
    ROLLBACK
The previous SQL snapshot therefore remains unchanged.
Important TechnicalIndicators rule
-----------------------------------
TechnicalIndicators has this primary key:
    PRIMARY KEY (Category, Ticker)
This is intentional.
The same ticker can exist in more than one category.
Example:
    ^NSEI + MarketIndices
    ^NSEI + GlobalMarkets
These are two valid rows and must NOT be treated as duplicates.
This file must NOT:
    - create or drop the database
    - create or drop tables
    - download data itself
    - read Excel itself
    - calculate indicators itself
    - calculate strength scores itself
    - calculate sentiment itself
The __main__ section only orchestrates the existing downloader/calculation
modules for a complete pipeline test.
Run:
    python -m database.update_database
"""
from __future__ import annotations
import logging
from typing import Iterable, Optional, Sequence
import pandas as pd

from database.connection import get_connection_context

logger = logging.getLogger(__name__)


# ==========================================================================
# VALUE CLEANING
# ==========================================================================
def _clean_value(value):
    """
    Convert pandas/numpy values into values that pyodbc can bind.

    NaN / NaT / None -> None
    numpy scalars -> native Python values
    pandas Timestamp -> datetime.date
    """
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, pd.Timestamp):
        return value.date()

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return value


def _rows_for_insert(
    df: pd.DataFrame,
    columns: Sequence[str],
) -> list[tuple]:
    """
    Convert a DataFrame into tuples in the exact SQL column order.

    Missing optional columns become NULL.
    """
    rows = []

    for _, record in df.iterrows():
        row = tuple(
            _clean_value(record[column]) if column in df.columns else None
            for column in columns
        )
        rows.append(row)

    return rows


# ==========================================================================
# SQL SCHEMA CHECK
# ==========================================================================
def _get_actual_columns(cursor, table_name: str) -> set[str]:
    """
    Read the actual SQL Server columns for dbo.<table_name>.
    """
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo'
          AND TABLE_NAME = ?;
        """,
        table_name,
    )

    return {row[0] for row in cursor.fetchall()}


def _preflight_check(cursor) -> None:
    """
    Check the live SQL schema before deleting any existing data.

    This prevents an UPDATE from deleting the existing snapshot and then
    discovering that the SQL table is missing a required column.
    """
    problems = []

    for table_name, columns in _TABLE_SPECS:
        actual_columns = _get_actual_columns(cursor, table_name)

        if not actual_columns:
            problems.append(
                f"dbo.{table_name} does not exist or could not be found."
            )
            continue

        missing = [
            column
            for column in columns
            if column not in actual_columns
        ]

        if missing:
            problems.append(
                f"dbo.{table_name} is missing column(s): {missing}"
            )

    if problems:
        details = "\n  - ".join(problems)

        raise RuntimeError(
            "update_database: SQL Server schema is out of sync with the "
            "pipeline.\n\n"
            "Problems:\n"
            f"  - {details}\n\n"
            "Run the current table_creation.sql in SSMS and retry."
        )


# ==========================================================================
# DATAFRAME VALIDATION
# ==========================================================================
def _validate_dataframe(
    df: Optional[pd.DataFrame],
    table_name: str,
    required_columns: Sequence[str],
) -> None:
    """
    Validate important DataFrame columns before SQL changes begin.
    """
    if df is None:
        logger.warning(
            "update_database: DataFrame for '%s' is None.",
            table_name,
        )
        return

    if df.empty:
        logger.warning(
            "update_database: DataFrame for '%s' is empty.",
            table_name,
        )
        return

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"{table_name} DataFrame is missing required column(s): "
            f"{missing}"
        )


def _validate_technical_indicators(
    technical_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """
    Validate and normalize the TechnicalIndicators DataFrame.

    SQL primary key:

        (Category, Ticker)

    Therefore duplicate checking MUST use both columns.

    A ticker appearing in two different categories is valid.
    """
    if technical_df is None:
        return pd.DataFrame()

    if technical_df.empty:
        return technical_df.copy()

    df = technical_df.copy()

    required = ["Ticker", "Category"]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            "TechnicalIndicators DataFrame is missing required column(s): "
            f"{missing}"
        )

    df["Ticker"] = (
        df["Ticker"]
        .astype(str)
        .str.strip()
    )

    df["Category"] = (
        df["Category"]
        .astype(str)
        .str.strip()
    )

    # Normalize category names to match the SQL/dashboard architecture.
    category_map = {
        "Market": "MarketIndices",
        "MarketIndex": "MarketIndices",
        "MarketIndices": "MarketIndices",
        "Global": "GlobalMarkets",
        "GlobalMarket": "GlobalMarkets",
        "GlobalMarkets": "GlobalMarkets",
        "Asset": "Assets",
        "Assets": "Assets",
    }

    df["Category"] = df["Category"].replace(category_map)

    invalid_categories = sorted(
        set(df["Category"].dropna())
        - {"MarketIndices", "GlobalMarkets", "Assets"}
    )

    if invalid_categories:
        raise ValueError(
            "TechnicalIndicators contains unknown Category value(s): "
            f"{invalid_categories}. "
            "Expected MarketIndices, GlobalMarkets or Assets."
        )

    # Remove rows with unusable primary-key values.
    df = df[
        df["Ticker"].notna()
        & df["Ticker"].ne("")
        & df["Category"].notna()
        & df["Category"].ne("")
    ].copy()

    # IMPORTANT:
    # Do NOT use df["Ticker"].duplicated() here.
    #
    # ^NSEI is allowed twice:
    #
    #   MarketIndices + ^NSEI
    #   GlobalMarkets + ^NSEI
    #
    duplicate_mask = df.duplicated(
        subset=["Category", "Ticker"],
        keep=False,
    )

    if duplicate_mask.any():
        duplicates = (
            df.loc[
                duplicate_mask,
                ["Category", "Ticker"]
            ]
            .value_counts()
            .reset_index(name="Count")
        )

        raise ValueError(
            "TechnicalIndicators contains duplicate SQL primary keys "
            "(Category, Ticker):\n"
            f"{duplicates.to_string(index=False)}"
        )

    return df.reset_index(drop=True)


def _add_current_prices(
    technical_df: pd.DataFrame,
    market_df: Optional[pd.DataFrame],
    global_df: Optional[pd.DataFrame],
    assets_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """
    Add CurrentPrice to TechnicalIndicators.

    The technical-indicator calculator calculates the indicator values
    from historical Close prices, while the downloader summary DataFrames
    already contain CurrentPrice.

    Match using both Category and Ticker so ^NSEI can exist in both:
        MarketIndices
        GlobalMarkets
    """
    if technical_df is None or technical_df.empty:
        return (
            technical_df.copy()
            if technical_df is not None
            else pd.DataFrame()
        )

    df = technical_df.copy()

    if "CurrentPrice" in df.columns:
        # Keep existing values if the technical module already supplied it.
        existing_price = df["CurrentPrice"].copy()
    else:
        existing_price = pd.Series(
            [None] * len(df),
            index=df.index,
            dtype="object",
        )

    price_frames = []

    def prepare_price_frame(
        source_df: Optional[pd.DataFrame],
        category: str,
    ):
        if source_df is None or source_df.empty:
            return None

        if "Ticker" not in source_df.columns:
            return None

        if "CurrentPrice" not in source_df.columns:
            return None

        temp = source_df[
            ["Ticker", "CurrentPrice"]
        ].copy()

        temp["Category"] = category

        return temp

    for source_df, category in (
        (market_df, "MarketIndices"),
        (global_df, "GlobalMarkets"),
        (assets_df, "Assets"),
    ):
        temp = prepare_price_frame(source_df, category)

        if temp is not None:
            price_frames.append(temp)

    if not price_frames:
        df["CurrentPrice"] = existing_price
        return df

    prices = pd.concat(
        price_frames,
        ignore_index=True,
    )

    prices = prices.drop_duplicates(
        subset=["Category", "Ticker"],
        keep="last",
    )

    prices = prices.rename(
        columns={"CurrentPrice": "_DownloaderCurrentPrice"}
    )

    df = df.merge(
        prices,
        on=["Category", "Ticker"],
        how="left",
    )

    df["CurrentPrice"] = existing_price

    missing_price = df["CurrentPrice"].isna()

    df.loc[
        missing_price,
        "CurrentPrice"
    ] = df.loc[
        missing_price,
        "_DownloaderCurrentPrice"
    ]

    df.drop(
        columns=["_DownloaderCurrentPrice"],
        inplace=True,
        errors="ignore",
    )

    return df


# ==========================================================================
# SQL DELETE / INSERT
# ==========================================================================
def _delete_table(cursor, table_name: str) -> None:
    """
    Delete the previous snapshot from a table.
    """
    cursor.execute(
        f"DELETE FROM dbo.{table_name};"
    )

    logger.info(
        "update_database: deleted previous snapshot from '%s'.",
        table_name,
    )


def _insert_table(
    cursor,
    table_name: str,
    columns: Sequence[str],
    df: Optional[pd.DataFrame],
) -> int:
    """
    Bulk-insert a DataFrame into SQL Server.
    """
    if df is None or df.empty:
        logger.warning(
            "update_database: no rows to insert into '%s'.",
            table_name,
        )
        return 0

    placeholders = ", ".join(
        ["?"] * len(columns)
    )

    column_list = ", ".join(columns)

    sql = (
        f"INSERT INTO dbo.{table_name} "
        f"({column_list}) "
        f"VALUES ({placeholders});"
    )

    rows = _rows_for_insert(
        df,
        columns,
    )

    if not rows:
        return 0

    cursor.fast_executemany = True
    cursor.executemany(
        sql,
        rows,
    )

    logger.info(
        "update_database: inserted %d row(s) into '%s'.",
        len(rows),
        table_name,
    )

    return len(rows)


# ==========================================================================
# SQL TABLE COLUMN DEFINITIONS
# ==========================================================================
MARKET_INDICES_COLUMNS = [
    "Ticker",
    "Name",
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

GLOBAL_MARKETS_COLUMNS = [
    "Ticker",
    "Name",
    "Country",
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

ASSETS_COLUMNS = [
    "Ticker",
    "Name",
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

# IMPORTANT:
# This matches the NEW TechnicalIndicators SQL table.
#
# SQL:
#
# Ticker
# Category
# CurrentPrice
# SMA20
# SMA100
# SMA200
# RSI14
# MACD
# MACDSignal
# MACDHistogram
# BollingerMiddle
# BollingerUpper
# BollingerLower
# MarketDate
# LastUpdated DEFAULT SYSDATETIME()
#
# Name is intentionally NOT included.
TECHNICAL_INDICATORS_COLUMNS = [
    "Ticker",
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

STRENGTH_SCORES_COLUMNS = [
    "Ticker",
    "Name",
    "Category",
    "StrengthScore",
    "RankWithinCategory",
    "Signal",
    "MarketDate",
]

MARKET_SENTIMENT_COLUMNS = [
    "Category",
    "MarketDate",
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
]

_TABLE_SPECS: Iterable[
    tuple[str, Sequence[str]]
] = (
    (
        "MarketIndices",
        MARKET_INDICES_COLUMNS,
    ),
    (
        "GlobalMarkets",
        GLOBAL_MARKETS_COLUMNS,
    ),
    (
        "Assets",
        ASSETS_COLUMNS,
    ),
    (
        "TechnicalIndicators",
        TECHNICAL_INDICATORS_COLUMNS,
    ),
    (
        "StrengthScores",
        STRENGTH_SCORES_COLUMNS,
    ),
    (
        "MarketSentiment",
        MARKET_SENTIMENT_COLUMNS,
    ),
)


# ==========================================================================
# MAIN DATABASE UPDATE
# ==========================================================================
def update_all_tables(
    market_indices_df: pd.DataFrame,
    global_markets_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    technical_indicators_df: pd.DataFrame,
    strength_scores_df: pd.DataFrame,
    market_sentiment_df: pd.DataFrame,
) -> bool:
    """
    Replace the previous SQL snapshot with the new pipeline snapshot.

    Everything is committed together in one transaction.

    Returns:
        True  -> successful commit
        False -> rollback
    """
    technical_indicators_df = _validate_technical_indicators(
        technical_indicators_df
    )

    technical_indicators_df = _add_current_prices(
        technical_indicators_df,
        market_indices_df,
        global_markets_df,
        assets_df,
    )

    dataframes = {
        "MarketIndices": market_indices_df,
        "GlobalMarkets": global_markets_df,
        "Assets": assets_df,
        "TechnicalIndicators": technical_indicators_df,
        "StrengthScores": strength_scores_df,
        "MarketSentiment": market_sentiment_df,
    }

    with get_connection_context() as conn:
        conn.autocommit = False
        cursor = conn.cursor()

        try:
            # Check the schema BEFORE deleting anything.
            _preflight_check(cursor)

            # Validate important columns before modifying SQL.
            _validate_dataframe(
                market_indices_df,
                "MarketIndices",
                ["Ticker"],
            )

            _validate_dataframe(
                global_markets_df,
                "GlobalMarkets",
                ["Ticker"],
            )

            _validate_dataframe(
                assets_df,
                "Assets",
                ["Ticker"],
            )

            _validate_dataframe(
                technical_indicators_df,
                "TechnicalIndicators",
                ["Ticker", "Category"],
            )

            _validate_dataframe(
                strength_scores_df,
                "StrengthScores",
                ["Ticker", "Category"],
            )

            _validate_dataframe(
                market_sentiment_df,
                "MarketSentiment",
                ["Category"],
            )

            total_inserted = 0

            for table_name, columns in _TABLE_SPECS:
                _delete_table(
                    cursor,
                    table_name,
                )

                total_inserted += _insert_table(
                    cursor,
                    table_name,
                    columns,
                    dataframes[table_name],
                )

            conn.commit()

            logger.info(
                "update_database: transaction committed successfully "
                "(%d total row(s) inserted across 6 tables).",
                total_inserted,
            )

            return True

        except Exception as exc:
            conn.rollback()

            logger.error(
                "update_database: transaction failed and was rolled back "
                "- previous snapshot is unchanged. Error: %s",
                exc,
            )

            return False


# ==========================================================================
# COMPLETE PIPELINE TEST
# ==========================================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO
    )

    print(
        "Running full pipeline + database update test..."
    )

    try:
        # ------------------------------------------------------------------
        # DOWNLOADERS
        # ------------------------------------------------------------------
        from downloaders.market_indices import (
            fetch_market_indices_data,
        )

        from downloaders.global_markets import (
            get_global_markets_data,
        )

        from downloaders.assets import (
            get_assets_data,
        )

        print("\nDownloading Market Indices...")
        market_df = fetch_market_indices_data()

        print("\nDownloading Global Markets...")
        global_df = get_global_markets_data()

        print("\nDownloading Assets...")
        assets_df = get_assets_data()

        # ------------------------------------------------------------------
        # TECHNICAL INDICATORS
        # ------------------------------------------------------------------
        #
        # IMPORTANT:
        # The current technical_indicators.py provides:
        #
        #     get_all_technical_indicators()
        #
        # instead of requiring update_database.py to import three separate
        # functions.
        #
        # This fixes the ImportError:
        #
        # cannot import name
        # 'get_market_indices_technical_indicators'
        #
        # ------------------------------------------------------------------
        from calculations.technical_indicators import (
            get_market_indices_technical_indicators,
            get_global_markets_technical_indicators,
            get_assets_technical_indicators,
        )

        print("\nCalculating Technical Indicators...")

        technical_df = get_market_indices_technical_indicators()

        if technical_df is None:
            technical_df = pd.DataFrame()

        print(
            f"Technical indicator rows produced: "
            f"{len(technical_df)}"
        )

        # ------------------------------------------------------------------
        # NORMALIZE TECHNICAL DATA
        # ------------------------------------------------------------------
        technical_df = _validate_technical_indicators(
            technical_df
        )

        technical_df = _add_current_prices(
            technical_df,
            market_df,
            global_df,
            assets_df,
        )

        # ------------------------------------------------------------------
        # IMPORTANT DUPLICATE CHECK
        # ------------------------------------------------------------------
        #
        # We check Category + Ticker, NOT Ticker alone.
        #
        # Therefore:
        #
        # MarketIndices   ^NSEI   -> valid
        # GlobalMarkets   ^NSEI   -> valid
        #
        # But:
        #
        # MarketIndices   ^NSEI   -> duplicate
        # MarketIndices   ^NSEI   -> duplicate
        #
        print(
            "\n===== TECHNICAL INDICATORS PRIMARY KEY CHECK ====="
        )

        print(
            f"Technical rows: {len(technical_df)}"
        )

        if not technical_df.empty:
            duplicate_mask = technical_df.duplicated(
                subset=["Category", "Ticker"],
                keep=False,
            )

            if duplicate_mask.any():
                print(
                    "\nDUPLICATE (Category, Ticker) KEYS FOUND:"
                )

                print(
                    technical_df.loc[
                        duplicate_mask,
                        ["Category", "Ticker"],
                    ].to_string(index=False)
                )

                raise ValueError(
                    "Duplicate TechnicalIndicators primary keys found."
                )

            print(
                "No duplicate (Category, Ticker) keys found."
            )

            # Show the important ^NSEI situation if it exists.
            nsei_rows = technical_df[
                technical_df["Ticker"].eq("^NSEI")
            ]

            if not nsei_rows.empty:
                print(
                    "\n^NSEI category check:"
                )

                print(
                    nsei_rows[
                        ["Ticker", "Category"]
                    ].to_string(index=False)
                )

        # ------------------------------------------------------------------
        # STRENGTH SCORES
        # ------------------------------------------------------------------
        from calculations.strength_score import (
            get_all_strength_scores,
        )

        print(
            "\nCalculating Strength Scores..."
        )

        # The strength-score module currently receives the three
        # category-specific technical DataFrames.
        #
        # Build them from the combined TechnicalIndicators DataFrame.
        market_tech = technical_df[
            technical_df["Category"].eq("MarketIndices")
        ].copy()

        global_tech = technical_df[
            technical_df["Category"].eq("GlobalMarkets")
        ].copy()

        assets_tech = technical_df[
            technical_df["Category"].eq("Assets")
        ].copy()

        strength_df = get_all_strength_scores(
            market_df,
            market_tech,
            global_df,
            global_tech,
            assets_df,
            assets_tech,
        )

        if strength_df is None:
            strength_df = pd.DataFrame()

        # ------------------------------------------------------------------
        # MARKET SENTIMENT
        # ------------------------------------------------------------------
        from calculations.market_sentiment import (
            get_market_sentiment,
        )

        print(
            "\nCalculating Market Sentiment..."
        )

        sentiment_df = get_market_sentiment(
            market_df,
            global_df,
            assets_df,
        )

        if sentiment_df is None:
            sentiment_df = pd.DataFrame()

        # ------------------------------------------------------------------
        # DATABASE UPDATE
        # ------------------------------------------------------------------
        print(
            "\nUpdating SQL Server..."
        )

        success = update_all_tables(
            market_df,
            global_df,
            assets_df,
            technical_df,
            strength_df,
            sentiment_df,
        )

        if success:
            print(
                "\nDatabase update SUCCEEDED."
            )
        else:
            print(
                "\nDatabase update FAILED - rolled back."
            )

    except Exception as exc:
        logger.exception(
            "Full pipeline test failed: %s",
            exc,
        )

        print(
            "\nDatabase update FAILED."
        )
        print(
            f"Error: {exc}"
        )