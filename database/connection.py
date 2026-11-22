"""
database/connection.py
STEP 2 of the STOCK_MARKET_DASHBOARD pipeline.
Purpose
-------
Create and manage the SQL Server connection to `Market_Intelligence`.
This file must NOT:
    - download Yahoo/yfinance data
    - read Excel
    - calculate indicators
    - insert or delete business data (that belongs to database/update_database.py)
It only knows how to open, verify, and close a pyodbc connection.
"""
import logging
from contextlib import contextmanager
import pyodbc
from config.config import CONFIG
logger = logging.getLogger(__name__)
def _build_connection_string() -> str:
    """Build the ODBC connection string from config.config settings."""
    parts = [
        f"DRIVER={CONFIG.SQL_DRIVER}",
        f"SERVER={CONFIG.SQL_SERVER}",
        f"DATABASE={CONFIG.SQL_DATABASE}",
    ]
    if CONFIG.SQL_TRUSTED_CONNECTION:
        parts.append("Trusted_Connection=yes")
    else:
        if not CONFIG.SQL_USERNAME or not CONFIG.SQL_PASSWORD:
            raise ValueError(
                "SQL authentication is enabled (MARKET_SQL_TRUSTED=false) but "
                "MARKET_SQL_USERNAME / MARKET_SQL_PASSWORD are not set."
            )
        parts.append(f"UID={CONFIG.SQL_USERNAME}")
        parts.append(f"PWD={CONFIG.SQL_PASSWORD}")
    return ";".join(parts) + ";"
def get_connection() -> pyodbc.Connection:
    """
    Open and return a live pyodbc connection to Market_Intelligence.
    Raises
    ------
    RuntimeError
        If the connection cannot be established, with the underlying
        pyodbc error preserved in the message for debugging.
    """
    conn_str = _build_connection_string()
    try:
        connection = pyodbc.connect(
            conn_str, timeout=CONFIG.SQL_CONNECT_TIMEOUT_SECONDS
        )
        logger.info(
            "Connected to SQL Server '%s', database '%s'.",
            CONFIG.SQL_SERVER,
            CONFIG.SQL_DATABASE,
        )
        return connection
    except pyodbc.Error as exc:
        logger.error(
            "Failed to connect to SQL Server '%s', database '%s': %s",
            CONFIG.SQL_SERVER,
            CONFIG.SQL_DATABASE,
            exc,
        )
        raise RuntimeError(
            f"Could not connect to SQL Server database '{CONFIG.SQL_DATABASE}' "
            f"on server '{CONFIG.SQL_SERVER}'. Check config/config.py or the "
            f"MARKET_SQL_* environment variables."
        ) from exc
@contextmanager
def get_connection_context():
    """
    Context-manager version of get_connection(), for safe use with `with`:
        from database.connection import get_connection_context
        with get_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
    Guarantees the connection is closed even if an exception is raised.
    Does NOT commit or rollback automatically — that responsibility stays
    with database/update_database.py, which owns the transaction logic.
    """
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()
        logger.info("SQL Server connection closed.")
def test_connection() -> bool:
    """
    Lightweight health check: opens a connection, runs `SELECT 1`, closes it.
    Returns True if the database is reachable, False otherwise.
    Useful for Phase 1 testing (README section 28) before any other module
    depends on the database.
    """
    try:
        with get_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except RuntimeError as exc:
        logger.error("Connection test failed: %s", exc)
        return False
if __name__ == "__main__":
    # Quick manual sanity check: `python database/connection.py`
    logging.basicConfig(level=logging.INFO)
    ok = test_connection()
    print("SQL Server connection OK" if ok else "SQL Server connection FAILED")