USE Market_Intelligence;
GO

IF OBJECT_ID('dbo.MarketIndices', 'U') IS NOT NULL
    DROP TABLE dbo.MarketIndices;
GO

IF OBJECT_ID('dbo.GlobalMarkets', 'U') IS NOT NULL
    DROP TABLE dbo.GlobalMarkets;
GO

IF OBJECT_ID('dbo.Assets', 'U') IS NOT NULL
    DROP TABLE dbo.Assets;
GO

IF OBJECT_ID('dbo.TechnicalIndicators', 'U') IS NOT NULL
    DROP TABLE dbo.TechnicalIndicators;
GO

IF OBJECT_ID('dbo.StrengthScores', 'U') IS NOT NULL
    DROP TABLE dbo.StrengthScores;
GO

IF OBJECT_ID('dbo.MarketSentiment', 'U') IS NOT NULL
    DROP TABLE dbo.MarketSentiment;
GO

CREATE TABLE dbo.MarketIndices
(
    Ticker NVARCHAR(50) NOT NULL PRIMARY KEY,
    Name NVARCHAR(150) NOT NULL,
    CurrentPrice DECIMAL(18,4) NULL,
    Change1D DECIMAL(10,4) NULL,
    Change1W DECIMAL(10,4) NULL,
    Change1M DECIMAL(10,4) NULL,
    Change3M DECIMAL(10,4) NULL,
    Change6M DECIMAL(10,4) NULL,
    Change1Y DECIMAL(10,4) NULL,
    Change3Y DECIMAL(10,4) NULL,
    Change5Y DECIMAL(10,4) NULL,
    MarketDate DATE NULL,
    LastUpdated DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
);
GO

CREATE TABLE dbo.GlobalMarkets
(
    Ticker NVARCHAR(50) NOT NULL PRIMARY KEY,
    Name NVARCHAR(50) NOT NULL,
    Country NVARCHAR(50) NULL,
    CurrentPrice DECIMAL(18,4) NULL,
    Change1D DECIMAL(10,4) NULL,
    Change1W DECIMAL(10,4) NULL,
    Change1M DECIMAL(10,4) NULL,
    Change3M DECIMAL(10,4) NULL,
    Change6M DECIMAL(10,4) NULL,
    Change1Y DECIMAL(10,4) NULL,
    Change3Y DECIMAL(10,4) NULL,
    Change5Y DECIMAL(10,4) NULL,
    MarketDate DATE NULL,
    LastUpdated DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
);
GO

CREATE TABLE dbo.Assets
(
    Ticker NVARCHAR(50) NOT NULL PRIMARY KEY,
    Name NVARCHAR(150) NOT NULL,
    CurrentPrice DECIMAL(18,4) NULL,
    Change1D DECIMAL(10,4) NULL,
    Change1W DECIMAL(10,4) NULL,
    Change1M DECIMAL(10,4) NULL,
    Change3M DECIMAL(10,4) NULL,
    Change6M DECIMAL(10,4) NULL,
    Change1Y DECIMAL(10,4) NULL,
    Change3Y DECIMAL(10,4) NULL,
    Change5Y DECIMAL(10,4) NULL,
    MarketDate DATE NULL,
    LastUpdated DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
);
GO

CREATE TABLE dbo.TechnicalIndicators
(
    Ticker NVARCHAR(50) NOT NULL,
    Category NVARCHAR(20) NOT NULL,
    CurrentPrice DECIMAL(18,4) NULL,
    SMA20 DECIMAL(18,4) NULL,
    SMA100 DECIMAL(18,4) NULL,
    SMA200 DECIMAL(18,4) NULL,
    RSI14 DECIMAL(10,4) NULL,
    MACD DECIMAL(18,6) NULL,
    MACDSignal DECIMAL(18,6) NULL,
    MACDHistogram DECIMAL(18,6) NULL,
    BollingerMiddle DECIMAL(18,4) NULL,
    BollingerUpper DECIMAL(18,4) NULL,
    BollingerLower DECIMAL(18,4) NULL,
    MarketDate DATE NULL,
    LastUpdated DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT PK_TechnicalIndicators
    PRIMARY KEY (Category, Ticker)
);
GO

CREATE TABLE dbo.StrengthScores
(
    Ticker NVARCHAR(50) NOT NULL,
    Name NVARCHAR(150) NOT NULL,
    Category NVARCHAR(30) NOT NULL,
    StrengthScore DECIMAL(10,2) NULL,
    RankWithinCategory INT NULL,
    Signal NVARCHAR(20) NULL,
    MarketDate DATE NULL,
    LastUpdated DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),

    CONSTRAINT PK_StrengthScores
        PRIMARY KEY (Category, Ticker),

    CONSTRAINT CK_StrengthScores_Category
        CHECK (Category IN ('Nifty', 'Global', 'Assets'))
);
GO

CREATE TABLE dbo.MarketSentiment
(
    Category NVARCHAR(30) NOT NULL,
    MarketDate DATE NOT NULL,

    BullishCount INT NOT NULL DEFAULT 0,
    NeutralCount INT NOT NULL DEFAULT 0,
    BearishCount INT NOT NULL DEFAULT 0,
    TotalCount INT NOT NULL DEFAULT 0,

    BullishPercentage DECIMAL(10,2) NULL,
    NeutralPercentage DECIMAL(10,2) NULL,
    BearishPercentage DECIMAL(10,2) NULL,

    GreenCount INT NOT NULL DEFAULT 0,
    RedCount INT NOT NULL DEFAULT 0,
    NeutralChangeCount INT NOT NULL DEFAULT 0,

    GreenPercentage DECIMAL(10,2) NULL,
    RedPercentage DECIMAL(10,2) NULL,
    NeutralChangePercentage DECIMAL(10,2) NULL,

    OverallSentiment NVARCHAR(20) NULL,

    LastUpdated DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),

    CONSTRAINT PK_MarketSentiment
        PRIMARY KEY (Category, MarketDate),

    CONSTRAINT CK_MarketSentiment_Category
        CHECK (Category IN ('Nifty', 'Global', 'Assets'))
);
GO