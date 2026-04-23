from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import yfinance as yf
import os
from .stockstats_utils import StockstatsUtils, _clean_dataframe, yf_retry, load_ohlcv, filter_financials_by_date

_VOLUME_WINDOW = 20
_INDICATOR_ALIASES = {
    "relative_volume": "rvol",
    "rel_volume": "rvol",
    "volume_z_score": "volume_zscore",
    "vol_zscore": "volume_zscore",
    "volume_slope": "volume_trend_slope",
    "vol_slope": "volume_trend_slope",
}
_CUSTOM_VOLUME_INDICATORS = {
    "rvol",
    "volume_zscore",
    "volume_trend_slope",
}


def _normalize_indicator_name(indicator: str) -> str:
    """Normalize aliases so users can request indicators with common variants."""
    normalized = str(indicator).strip().lower()
    return _INDICATOR_ALIASES.get(normalized, normalized)


def _compute_rvol(volume: pd.Series, window: int = _VOLUME_WINDOW) -> pd.Series:
    rolling_mean = volume.rolling(window=window, min_periods=window).mean()
    return volume / rolling_mean.replace(0, pd.NA)


def _compute_volume_zscore(volume: pd.Series, window: int = _VOLUME_WINDOW) -> pd.Series:
    rolling_mean = volume.rolling(window=window, min_periods=window).mean()
    rolling_std = volume.rolling(window=window, min_periods=window).std()
    return (volume - rolling_mean) / rolling_std.replace(0, pd.NA)


def _compute_volume_trend_slope(volume: pd.Series, window: int = _VOLUME_WINDOW) -> pd.Series:
    n = window
    sum_x = n * (n - 1) / 2
    sum_x2 = (n - 1) * n * (2 * n - 1) / 6
    denominator = n * sum_x2 - (sum_x ** 2)

    def slope_ratio(values) -> float:
        if len(values) != n:
            return float("nan")
        sum_y = float(sum(values))
        mean_y = sum_y / n
        if mean_y == 0:
            return float("nan")

        sum_xy = 0.0
        for i, value in enumerate(values):
            sum_xy += i * float(value)

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return slope / mean_y

    return volume.rolling(window=window, min_periods=window).apply(
        slope_ratio,
        raw=True,
    )


def _compute_custom_volume_indicator(data: pd.DataFrame, indicator: str) -> pd.Series:
    """Compute non-stockstats volume indicators from OHLCV data."""
    volume = pd.to_numeric(data["Volume"], errors="coerce")

    if indicator == "rvol":
        return _compute_rvol(volume)
    if indicator == "volume_zscore":
        return _compute_volume_zscore(volume)
    if indicator == "volume_trend_slope":
        return _compute_volume_trend_slope(volume)

    raise ValueError(f"Unsupported custom indicator: {indicator}")

def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # Create ticker object
    ticker = yf.Ticker(symbol.upper())

    # yfinance 'end' is exclusive, so add 1 day to include end_date
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + relativedelta(days=1)
    end_date_inclusive = end_dt.strftime("%Y-%m-%d")

    # Fetch historical data for the specified date range
    data = yf_retry(lambda: ticker.history(start=start_date, end=end_date_inclusive))

    # Check if data is empty
    if data.empty:
        return (
            f"No data found for symbol '{symbol}' between {start_date} and {end_date}"
        )

    # Remove timezone info from index for cleaner output
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    # Round numerical values to 2 decimal places for cleaner display
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    # Convert DataFrame to CSV string
    csv_string = data.to_csv()

    # Add header information
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string

def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[
        str, "The current trading date you are trading on, YYYY-mm-dd"
    ],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:

    indicator = _normalize_indicator_name(indicator)

    best_ind_params = {
        # Moving Averages
        "close_50_sma": (
            "50 SMA: A medium-term trend indicator. "
            "Usage: Identify trend direction and serve as dynamic support/resistance. "
            "Tips: It lags price; combine with faster indicators for timely signals."
        ),
        "close_200_sma": (
            "200 SMA: A long-term trend benchmark. "
            "Usage: Confirm overall market trend and identify golden/death cross setups. "
            "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
        ),
        "close_10_ema": (
            "10 EMA: A responsive short-term average. "
            "Usage: Capture quick shifts in momentum and potential entry points. "
            "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
        ),
        # MACD Related
        "macd": (
            "MACD: Computes momentum via differences of EMAs. "
            "Usage: Look for crossovers and divergence as signals of trend changes. "
            "Tips: Confirm with other indicators in low-volatility or sideways markets."
        ),
        "macds": (
            "MACD Signal: An EMA smoothing of the MACD line. "
            "Usage: Use crossovers with the MACD line to trigger trades. "
            "Tips: Should be part of a broader strategy to avoid false positives."
        ),
        "macdh": (
            "MACD Histogram: Shows the gap between the MACD line and its signal. "
            "Usage: Visualize momentum strength and spot divergence early. "
            "Tips: Can be volatile; complement with additional filters in fast-moving markets."
        ),
        # Momentum Indicators
        "rsi": (
            "RSI: Measures momentum to flag overbought/oversold conditions. "
            "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
            "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
        ),
        # Volatility Indicators
        "boll": (
            "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
            "Usage: Acts as a dynamic benchmark for price movement. "
            "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
        ),
        "boll_ub": (
            "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
            "Usage: Signals potential overbought conditions and breakout zones. "
            "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
        ),
        "boll_lb": (
            "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
            "Usage: Indicates potential oversold conditions. "
            "Tips: Use additional analysis to avoid false reversal signals."
        ),
        "atr": (
            "ATR: Averages true range to measure volatility. "
            "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
            "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
        ),
        # Volume-Based Indicators
        "vwma": (
            "VWMA: A moving average weighted by volume. "
            "Usage: Confirm trends by integrating price action with volume data. "
            "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
        ),
        "mfi": (
            "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
            "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
            "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
        ),
        "rvol": (
            "RVOL (Relative Volume): Current bar's volume divided by the trailing 20-bar simple average volume (window inclusive of the current bar). "
            "Usage: Identify unusual participation and confirm breakout/breakdown conviction. "
            "Tips: Values >1 imply above-normal activity (e.g. 1.5 = 50% heavier than typical); pair with price structure to avoid false signals."
        ),
        "volume_zscore": (
            "Volume Z-Score: (current volume - 20-bar mean) / 20-bar sample standard deviation, i.e. how many standard deviations the latest volume sits from its trailing 20-bar mean. "
            "Usage: Quantify whether volume is statistically extreme versus recent behavior. "
            "Tips: |z| > 2 typically flags an outlier session; near-zero suggests normal conditions."
        ),
        "volume_trend_slope": (
            "Volume Trend Slope: OLS linear-regression slope of volume against bar index over the last 20 bars, divided by the 20-bar mean volume (i.e. an approximate per-bar fractional growth rate of volume). "
            "Usage: Detect whether participation is accelerating or fading over time. "
            "Tips: Positive values mean rising engagement, negative values mean weakening interest; magnitude is comparable across tickers because it is mean-normalized."
        ),
    }

    if indicator not in best_ind_params:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(best_ind_params.keys())}"
        )

    end_date = curr_date
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    # Optimized: Get stock data once and calculate indicators for all dates
    try:
        indicator_data = _get_stock_stats_bulk(symbol, indicator, curr_date)
        
        # Generate the date range we need
        current_dt = curr_date_dt
        date_values = []
        
        while current_dt >= before:
            date_str = current_dt.strftime('%Y-%m-%d')
            
            # Look up the indicator value for this date
            if date_str in indicator_data:
                indicator_value = indicator_data[date_str]
            else:
                indicator_value = "N/A: Not a trading day (weekend or holiday)"
            
            date_values.append((date_str, indicator_value))
            current_dt = current_dt - relativedelta(days=1)
        
        # Build the result string
        ind_string = ""
        for date_str, value in date_values:
            ind_string += f"{date_str}: {value}\n"
        
    except Exception as e:
        print(f"Error getting bulk stockstats data: {e}")
        # Fallback to original implementation if bulk method fails
        ind_string = ""
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        while curr_date_dt >= before:
            indicator_value = get_stockstats_indicator(
                symbol, indicator, curr_date_dt.strftime("%Y-%m-%d")
            )
            if not str(indicator_value).strip():
                indicator_value = f"N/A: Error retrieving {indicator}"
            ind_string += f"{curr_date_dt.strftime('%Y-%m-%d')}: {indicator_value}\n"
            curr_date_dt = curr_date_dt - relativedelta(days=1)

    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "No description available.")
    )

    return result_str


def _get_stock_stats_bulk(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "current date for reference"]
) -> dict:
    """
    Optimized bulk calculation of stock stats indicators.
    Fetches data once and calculates indicator for all available dates.
    Returns dict mapping date strings to indicator values.
    """
    from stockstats import wrap

    indicator = _normalize_indicator_name(indicator)

    data = load_ohlcv(symbol, curr_date)
    data = data.copy()
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"]).sort_values("Date")

    if indicator in _CUSTOM_VOLUME_INDICATORS:
        metric_values = _compute_custom_volume_indicator(data, indicator)
        df = pd.DataFrame(
            {
                "Date": data["Date"].dt.strftime("%Y-%m-%d"),
                indicator: metric_values,
            }
        )
    else:
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        # Calculate the indicator for all rows at once
        df[indicator]  # This triggers stockstats to calculate the indicator
    
    # Create a dictionary mapping date strings to indicator values
    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        indicator_value = row[indicator]
        
        # Handle NaN/None values
        if pd.isna(indicator_value) or indicator_value in (float("inf"), float("-inf")):
            result_dict[date_str] = "N/A"
        else:
            result_dict[date_str] = str(indicator_value)
    
    return result_dict


def get_stockstats_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[
        str, "The current trading date you are trading on, YYYY-mm-dd"
    ],
) -> str:

    indicator = _normalize_indicator_name(indicator)

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    curr_date = curr_date_dt.strftime("%Y-%m-%d")

    try:
        if indicator in _CUSTOM_VOLUME_INDICATORS:
            indicator_values = _get_stock_stats_bulk(symbol, indicator, curr_date)
            return indicator_values.get(curr_date, "N/A: Not a trading day (weekend or holiday)")

        indicator_value = StockstatsUtils.get_stock_stats(
            symbol,
            indicator,
            curr_date,
        )
    except Exception as e:
        print(
            f"Error getting stockstats indicator data for indicator {indicator} on {curr_date}: {e}"
        )
        return f"N/A: Error retrieving {indicator}"

    return str(indicator_value)


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None
):
    """Get company fundamentals overview from yfinance.

    For ETFs, transparently delegates to ``get_etf_profile`` so callers that
    are unaware of the instrument type still receive useful data instead of
    an equity field list full of blanks.
    """
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = yf_retry(lambda: ticker_obj.info)

        if not info:
            return f"No fundamentals data found for symbol '{ticker}'"

        if str(info.get("quoteType", "")).upper() == "ETF":
            from .y_finance_etf import get_etf_profile
            return get_etf_profile(ticker, curr_date)

        fields = [
            ("Name", info.get("longName")),
            ("Sector", info.get("sector")),
            ("Industry", info.get("industry")),
            ("Market Cap", info.get("marketCap")),
            ("PE Ratio (TTM)", info.get("trailingPE")),
            ("Forward PE", info.get("forwardPE")),
            ("PEG Ratio", info.get("pegRatio")),
            ("Price to Book", info.get("priceToBook")),
            ("EPS (TTM)", info.get("trailingEps")),
            ("Forward EPS", info.get("forwardEps")),
            ("Dividend Yield", info.get("dividendYield")),
            ("Beta", info.get("beta")),
            ("52 Week High", info.get("fiftyTwoWeekHigh")),
            ("52 Week Low", info.get("fiftyTwoWeekLow")),
            ("50 Day Average", info.get("fiftyDayAverage")),
            ("200 Day Average", info.get("twoHundredDayAverage")),
            ("Revenue (TTM)", info.get("totalRevenue")),
            ("Gross Profit", info.get("grossProfits")),
            ("EBITDA", info.get("ebitda")),
            ("Net Income", info.get("netIncomeToCommon")),
            ("Profit Margin", info.get("profitMargins")),
            ("Operating Margin", info.get("operatingMargins")),
            ("Return on Equity", info.get("returnOnEquity")),
            ("Return on Assets", info.get("returnOnAssets")),
            ("Debt to Equity", info.get("debtToEquity")),
            ("Current Ratio", info.get("currentRatio")),
            ("Book Value", info.get("bookValue")),
            ("Free Cash Flow", info.get("freeCashflow")),
        ]

        lines = []
        for label, value in fields:
            if value is not None:
                lines.append(f"{label}: {value}")

        header = f"# Company Fundamentals for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + "\n".join(lines)

    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get balance sheet data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_balance_sheet)
        else:
            data = yf_retry(lambda: ticker_obj.balance_sheet)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            return f"No balance sheet data found for symbol '{ticker}'"
            
        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()
        
        # Add header information
        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get cash flow data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_cashflow)
        else:
            data = yf_retry(lambda: ticker_obj.cashflow)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            return f"No cash flow data found for symbol '{ticker}'"
            
        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()
        
        # Add header information
        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get income statement data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_income_stmt)
        else:
            data = yf_retry(lambda: ticker_obj.income_stmt)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            return f"No income statement data found for symbol '{ticker}'"
            
        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()
        
        # Add header information
        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"]
):
    """Get insider transactions data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = yf_retry(lambda: ticker_obj.insider_transactions)
        
        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"
            
        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()
        
        # Add header information
        header = f"# Insider Transactions data for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"


def get_analyst_recommendations(
    ticker: Annotated[str, "ticker symbol of the company"]
):
    """Get Wall Street analyst recommendations and price targets from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        sections = []

        # Price targets
        try:
            targets = yf_retry(lambda: ticker_obj.analyst_price_targets)
            if targets is not None and not (isinstance(targets, pd.DataFrame) and targets.empty):
                sections.append(f"## Analyst Price Targets for {ticker.upper()}")
                if isinstance(targets, dict):
                    for k, v in targets.items():
                        if v is not None:
                            sections.append(f"{k}: {v}")
                else:
                    sections.append(str(targets))
        except Exception:
            pass

        # Recommendations summary
        try:
            recs = yf_retry(lambda: ticker_obj.recommendations)
            if recs is not None and not recs.empty:
                sections.append(f"\n## Recent Analyst Recommendations for {ticker.upper()}")
                sections.append(recs.head(20).to_csv())
        except Exception:
            pass

        # Upgrades / downgrades
        try:
            upgrades = yf_retry(lambda: ticker_obj.upgrades_downgrades)
            if upgrades is not None and not upgrades.empty:
                sections.append(f"\n## Recent Upgrades/Downgrades for {ticker.upper()}")
                sections.append(upgrades.head(20).to_csv())
        except Exception:
            pass

        if not sections:
            return f"No analyst recommendation data found for symbol '{ticker}'"

        header = f"# Analyst Recommendations for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + "\n".join(sections)

    except Exception as e:
        return f"Error retrieving analyst recommendations for {ticker}: {str(e)}"


def get_live_quote(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Get a near-real-time quote snapshot (~15 min delayed) from yfinance.

    Returns last price, day range, volume, previous close, and percent change.
    Useful mid-trading-day when daily OHLCV bars only reflect the open.
    """
    try:
        t = yf.Ticker(ticker.upper())
        fi = t.fast_info

        last = fi.get("lastPrice")
        prev_close = fi.get("previousClose")
        day_high = fi.get("dayHigh")
        day_low = fi.get("dayLow")
        last_volume = fi.get("lastVolume")
        mkt_cap = fi.get("marketCap")

        if last is None:
            return f"No live quote available for '{ticker}'"

        pct_change = ""
        if prev_close and prev_close != 0:
            change = ((last - prev_close) / prev_close) * 100
            pct_change = f"Change from prev close: {change:+.2f}%\n"

        header = f"# Live Quote Snapshot for {ticker.upper()}\n"
        header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (delayed ~15 min)\n\n"

        lines = [
            f"Last Price: {last:.2f}" if last else None,
            f"Previous Close: {prev_close:.2f}" if prev_close else None,
            pct_change.strip() if pct_change else None,
            f"Day Range: {day_low:.2f} - {day_high:.2f}" if day_low and day_high else None,
            f"Volume: {last_volume:,.0f}" if last_volume else None,
            f"Market Cap: {mkt_cap:,.0f}" if mkt_cap else None,
        ]

        return header + "\n".join(l for l in lines if l)

    except Exception as e:
        return f"Error retrieving live quote for {ticker}: {str(e)}"