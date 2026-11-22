Copyright (c) 2026 Navdeep Kaur.
All rights reserved.

This repository is published for viewing and
educational evaluation purposes only.
No permission is granted to copy, modify,
distribute, or commercially use this code.

# Stock Market Dashboard – Data Pipeline

A Python project that collects market data every time you run it, calculates useful numbers from that data, and saves everything into a SQL Server database. A dashboard tool (such as Power BI) can then read the database and show charts.

**Run one command, get a fresh snapshot of the markets:**

```bash
python main.py
```

---
Here's the output screenshots of the project

<img width="1917" height="1093" alt="image" src="https://github.com/user-attachments/assets/413eebab-4608-4ca4-8ee2-fd7636b6d128" />

<img width="1917" height="1095" alt="image" src="https://github.com/user-attachments/assets/372835b3-3030-44e8-82aa-309dff95d764" />

<img width="1917" height="1093" alt="image" src="https://github.com/user-attachments/assets/2df3c0c0-63b6-4180-b352-37bb3f9ccc09" />

<img width="1917" height="1093" alt="image" src="https://github.com/user-attachments/assets/7ddf1806-987d-47b6-8c98-f10e268ffc3d" />




## 1. What is this project? (Simple explanation)

Imagine you want to know, every morning:

- Are Indian stock markets going up or down?
- How are other countries' markets doing (USA, Japan, UK, etc.)?
- What about gold, silver, crude oil, Bitcoin and the dollar?
- Which of these is "strong" right now, and which is "weak"?
- Is the overall mood positive (bullish) or negative (bearish)?

Doing this by hand means opening many websites and doing a lot of maths. This project does it **automatically**:

1. **Reads a list** of things to track from an Excel file (`MARKET.xlsx`).
2. **Downloads** their prices from the internet.
3. **Calculates** how much each one went up or down over 1 day, 1 week, 1 month, up to 5 years.
4. **Calculates technical indicators** (standard tools traders use to judge trends).
5. **Gives each item a Strength Score** and ranks them.
6. **Measures market sentiment** (how many are green vs red).
7. **Saves everything** into a SQL Server database, replacing the old snapshot.

Think of it like a **factory assembly line**: raw material (prices) goes in at one end, and a clean, finished product (database tables) comes out the other end.

### Words you may not know

| Term                              | Meaning in plain language                                                                            |
|---                                |---                                                                                                   |
| **Index**                         | A single number that represents a group of stocks (e.g. Nifty 50 = the 50 biggest Indian companies). |
| **Ticker**                        | A short code for an item, like `^GSPC` for the S&P 500.                                              |
| **Change1D / 1W / 1M …**          | Percentage change over 1 day / 1 week / 1 month, and so on up to 5 years.                            |
| **SMA (Simple Moving Average)**   | The average price over the last N days (20, 100, 200). Shows the trend direction.                    |
| **RSI**                           | A 0–100 number. High means the price rose a lot recently; low means it fell a lot.                   |
| **MACD**                          | A trend-and-momentum indicator built from two averages.                                              |
| **Bollinger Bands**               | A "normal range" around the average price. Price outside it is unusual.                              |
| **Strength Score**                | One combined number for how strong an item looks. Higher is stronger.                                |
| **Bullish / Bearish**             | Bullish = prices rising (positive mood). Bearish = prices falling (negative mood).                   |
| **Snapshot**                      | The latest picture of the data. Each refresh replaces the old one.                                   |

---

## 2. The three categories

The project always keeps these three groups **separate** and never mixes them:

| Category                   | What it contains | Data source |
|---                         |---|---|
| **Nifty / Market Indices** | 8 Indian indices (Nifty 50, 100, 500, Midcap 50/150, Smallcap 100/250, Microcap 250) | Jugaad Data (NSE) |
| **Global Markets**         | World indices (S&P 500, Nikkei, DAX, FTSE, Hang Seng, etc.) with their country | Yahoo Finance (`yfinance`) |
| **Assets**                 | Gold, Silver, USD/INR, Brent Crude, Bitcoin, etc. | Yahoo Finance (`yfinance`) |

---

## 3. The pipeline (step by step)

```
                         MARKET.xlsx
              (list of what to track: names, tickers,
                   country, Active = Yes/No)
                              |
                              v
   +-----------------------------------------------------------+
   |  STEP 1: DOWNLOAD                                         |
   |  downloaders/market_indices.py  -> Nifty (Jugaad Data)    |
   |  downloaders/global_markets.py  -> Global (yfinance)      |
   |  downloaders/assets.py          -> Assets (yfinance)      |
   |  Output: price + Change1D ... Change5Y + MarketDate       |
   +-----------------------------------------------------------+
                              |
                              v
   +-----------------------------------------------------------+
   |  STEP 2: TECHNICAL INDICATORS                             |
   |  calculations/technical_indicators.py                     |
   |  SMA20/100/200, RSI14, MACD, Bollinger Bands              |
   +-----------------------------------------------------------+
                              |
                              v
   +-----------------------------------------------------------+
   |  STEP 3: SCORES AND SENTIMENT                             |
   |  calculations/strength_score.py    -> score, rank, signal |
   |  calculations/market_sentiment.py  -> bullish/bearish %   |
   +-----------------------------------------------------------+
                              |
                              v
   +-----------------------------------------------------------+
   |  STEP 4: SAVE TO SQL SERVER                               |
   |  database/update_database.py                              |
   |  Delete old rows -> Insert new rows -> Commit             |
   |  (if anything fails: Rollback, old data stays safe)       |
   +-----------------------------------------------------------+
                              |
                              v
                SQL Server database: Market_Intelligence
                              |
                              v
                 Power BI / any dashboard tool
```

`main.py` is the **conductor**. It does not download or calculate anything itself. It only calls each module in the correct order.

### What happens in each step

**Step 1 – Download.**
The program reads `MARKET.xlsx` fresh on every run (so you can add or switch off instruments just by editing Excel). For every row marked `Active = Yes`, it downloads about 6 years of daily prices. It then works out the current price and the percentage change over 1D, 1W, 1M, 3M, 6M, 1Y, 3Y and 5Y. If a download fails, that item is skipped. The project never inserts fake or zero values.

**Step 2 – Technical indicators.**
Using the historical prices, it calculates SMA20, SMA100, SMA200, RSI14, MACD (with signal and histogram) and Bollinger Bands for every instrument.

**Step 3 – Strength score and sentiment.**

*Strength Score* blends several things into one number:

| Part | Weight | What it looks at |
|---|---|---|
| Momentum | 35% | 1Y, 3Y and 5Y returns |
| Trend | 20% | Is price above its SMA20 / SMA100 / SMA200? |
| RSI | 20% | The RSI14 value |
| MACD | 15% | Direction and size of the MACD histogram |
| Bollinger | 10% | Where price sits inside its Bollinger range |

Items are then **ranked within their own category** and given a signal:

| Score | Signal |
|---|---|
| 75 and above | Strong Buy |
| 60 to 75 | Buy |
| 40 to 60 | Neutral |
| 25 to 40 | Sell |
| Below 25 | Strong Sell |

*Market Sentiment* is simple. Using only the last completed day's `Change1D`:

- Change above 0 → Bullish (green)
- Change below 0 → Bearish (red)
- Change equal to 0 → Neutral

It counts these for each category. If 65% or more are bullish the result is "Strongly Bullish", and likewise "Strongly Bearish" for 65% or more bearish. Otherwise it is Bullish, Bearish or Neutral, depending on which side is bigger.

**Step 4 – Save to SQL Server.**
All six tables are updated inside **one transaction**: delete the old rows, insert the new rows, then commit. If any problem happens, everything is rolled back, so your dashboard never sees half-updated data. Before deleting anything, the program also checks that the SQL tables have all the columns it needs.

---

## 4. Data flow (what data goes where)

| From | To | Data passed |
|---|---|---|
| `MARKET.xlsx` | Downloaders | Name, Ticker, Active, Country (global only), DataSource |
| Downloaders | Strength score, Sentiment, SQL | Name, Ticker, (Country), CurrentPrice, Change1D–Change5Y, MarketDate |
| Technical indicators | Strength score, SQL | Ticker, Category, SMA, RSI, MACD, Bollinger values |
| Strength score | SQL | Ticker, Name, Category, StrengthScore, Rank, Signal |
| Market sentiment | SQL | Counts and percentages per category, OverallSentiment |

### The 6 SQL tables

| Table | One row per | Key columns |
|---|---|---|
| `MarketIndices` | Nifty index | Ticker, Name, CurrentPrice, Change1D…Change5Y, MarketDate |
| `GlobalMarkets` | World index | Same as above, plus **Country** |
| `Assets` | Asset | Same as MarketIndices |
| `TechnicalIndicators` | Instrument in a category | SMA20/100/200, RSI14, MACD, Bollinger |
| `StrengthScores` | Instrument in a category | StrengthScore, RankWithinCategory, Signal |
| `MarketSentiment` | Category per date | Bullish/Neutral/Bearish counts and %, OverallSentiment |

Every table also has a `LastUpdated` column that is filled automatically by SQL Server.

---

## 5. Project structure

```
STOCK_MARKET_DASHBOARD/
├── main.py                       # Run this. Calls everything in order.
├── MARKET.xlsx                   # Master list of what to track.
├── config/
│   └── config.py                 # Paths, SQL settings, Excel column mapping.
├── utils/
│   └── helpers.py                # Logging, Excel reading, yfinance download, return maths.
├── downloaders/
│   ├── market_indices.py         # Nifty indices via Jugaad Data.
│   ├── global_markets.py         # World indices via yfinance.
│   └── assets.py                 # Gold, Silver, Bitcoin, etc. via yfinance.
├── calculations/
│   ├── technical_indicators.py   # SMA, RSI, MACD, Bollinger.
│   ├── strength_score.py         # Score, rank and signal.
│   └── market_sentiment.py       # Bullish / bearish counts.
├── database/
│   ├── connection.py             # Opens the SQL Server connection.
│   └── update_database.py        # Delete old, insert new, commit/rollback.
├── sql/
│   ├── database_creation.sql     # Database creation / truncate helpers.
│   ├── table_creation.sql        # Creates the 6 tables.
│   └── SQLQuery1.sql             # Handy column-check query.
└── logs/
    └── dashboard.log             # Created automatically on first run.
```

Each file has **one job** and does not do the job of another. For example, downloaders never write to SQL, and the SQL module never downloads data.

---

## 6. MARKET.xlsx layout

| Sheet | Important columns |
|---|---|
| `Market_Indices` | `Name`, `Ticker`, optional `DataSource` |
| `Global_Markets` | `Name`, `Ticker`, `Country/Region`, `Active` |
| `assets` | `AssetName`, `Tickers`, `Active` |

Set `Active` to `Yes` to include a row. Anything else (or `No`) skips it. If you rename a column in Excel, update the mapping in `config/config.py` (`EXCEL_COLUMN_MAP`).

---

## 7. Setup

### Requirements

- Python 3.10 or newer
- SQL Server (Express is fine) and the **ODBC Driver 17 for SQL Server**
- Internet connection

### Install Python packages

```bash
pip install pandas numpy yfinance jugaad-data pyodbc openpyxl python-dateutil
```

### Create the database

1. In SQL Server Management Studio, create a database named `Market_Intelligence`.
2. Run `table_creation.sql` to create the 6 tables.

> Warning: `table_creation.sql` drops and recreates the tables, so any existing data in them will be lost.

### Configure the connection

Defaults are in `config/config.py`. You can also override them with environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `MARKET_SQL_SERVER` | `localhost\SQLEXPRESS` | SQL Server instance |
| `MARKET_SQL_DATABASE` | `Market_Intelligence` | Database name |
| `MARKET_SQL_DRIVER` | `{ODBC Driver 17 for SQL Server}` | ODBC driver |
| `MARKET_SQL_TRUSTED` | `true` | Windows authentication |
| `MARKET_SQL_USERNAME` / `MARKET_SQL_PASSWORD` | empty | Only needed if trusted is `false` |
| `MARKET_EXCEL_PATH` | `MARKET.xlsx` in project root | Path to the Excel file |
| `MARKET_LOG_LEVEL` | `INFO` | Logging detail |

Test the connection:

```bash
python -m database.connection
```

---

## 8. How to run

**Full refresh (normal use):**

```bash
python main.py
```

**Test one piece at a time:**

```bash
python -m downloaders.market_indices
python -m downloaders.global_markets
python -m downloaders.assets
python -m calculations.market_sentiment
python -m database.update_database      # full pipeline test
```

When the run finishes, you will see either `Refresh completed successfully.` or `Refresh FAILED - see logs/dashboard.log for details.` Details are always in `logs/dashboard.log`.

---

## 9. Design rules this project follows

- **Never fake data.** If a download fails, that instrument is skipped, not filled with zeros.
- **Last completed trading day only.** Today's unfinished session is not used.
- **Categories stay separate.** Nifty, Global and Assets are ranked and measured independently.
- **All-or-nothing SQL update.** One transaction: commit on success, rollback on failure.
- **Excel is the source of truth** for what to track. SQL is never used as the ticker list.
- **Schema check before delete.** The old snapshot is never deleted if the new data cannot be saved.

---

## 10. Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| `Could not connect to SQL Server` | Check `MARKET_SQL_SERVER`, the ODBC driver name, and that SQL Server is running. |
| `SQL Server schema is out of sync` | A column is missing in a table. Re-run `table_creation.sql`. |
| `MARKET.xlsx not found` | Put the file in the project root or set `MARKET_EXCEL_PATH`. |
| An instrument is missing in SQL | Its download failed or `Active` is not `Yes`. Check `logs/dashboard.log`. |
| `Country` is NULL in `GlobalMarkets` | Make sure `config.py` maps `"country": "Country/Region"`, and that `helpers.py` and `global_markets.py` carry the Country column through. |
| `ModuleNotFoundError` | Run commands from the project root using `python -m folder.file`, and make sure each folder is importable. |

---

## 11. Notes and possible improvements

- `technical_indicators.py` downloads fresh history for its own calculations. `main.py` calls its three category functions one after another, so the same download can run more than once per refresh. Fetching once and splitting the result by category would make refreshes faster.
- The Strength Score weights (35/20/20/15/10) are a starting point. They are defined as constants at the top of `strength_score.py` and are easy to change.
- Yahoo Finance data can occasionally be delayed or missing. The retry logic handles most temporary failures.

---

*This project reads and processes market data for information and learning only. It is not financial advice.*
