from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data,
    get_live_quote
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_analyst_recommendations
)
from tradingagents.agents.utils.etf_data_tools import (
    get_etf_profile,
    get_etf_holdings,
    get_etf_sector_weights,
    get_etf_correlation,
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def detect_instrument_kind(ticker: str) -> tuple[str, dict]:
    """Return ``(kind, info)`` where kind is ``"etf"``, ``"equity"``, or ``"unknown"``.

    ``info`` is the raw ``yfinance`` ``info`` dict (or ``{}`` on failure) so callers
    can reuse it without making a second network round-trip.
    """
    import yfinance as yf

    try:
        info = yf.Ticker(ticker.upper()).info or {}
    except Exception:
        return "unknown", {}

    quote_type = str(info.get("quoteType", "")).upper()
    if quote_type == "ETF":
        return "etf", info
    if quote_type in {"EQUITY", "STOCK"}:
        return "equity", info
    return "unknown", info


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers.
    
    Detects ETFs and adds context so analysts adjust their methodology accordingly.
    """
    base = (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

    kind, info = detect_instrument_kind(ticker)
    if kind != "etf":
        return base

    etf_name = info.get("longName") or info.get("shortName") or ticker
    category = info.get("category", "Unknown")
    total_assets = info.get("totalAssets")
    expense_ratio = info.get("netExpenseRatio") or info.get("annualReportExpenseRatio")
    parts = [f"category: {category}"]
    if total_assets:
        parts.append(f"AUM ~{total_assets:,.0f}")
    if expense_ratio:
        try:
            parts.append(f"expense ratio {float(expense_ratio):.2f}%")
        except (TypeError, ValueError):
            pass
    summary = ", ".join(parts)

    etf_context = (
        f"\n\nIMPORTANT: `{ticker}` is an ETF ({etf_name}); {summary}. "
        "Treat it as a basket, not an operating company: focus on holdings concentration, "
        "sector/thematic exposure, expense ratio, distribution yield, NAV premium/discount, "
        "and benchmark correlation. Use ETF-specific tools (`get_etf_profile`, "
        "`get_etf_holdings`, `get_etf_sector_weights`, `get_etf_correlation`) instead of "
        "single-company tools. Earnings, P/E, and insider transactions do not apply."
    )
    return base + etf_context

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
