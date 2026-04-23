from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    detect_instrument_kind,
    get_analyst_recommendations,
    get_balance_sheet,
    get_cashflow,
    get_etf_correlation,
    get_etf_holdings,
    get_etf_profile,
    get_etf_sector_weights,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
)
from tradingagents.dataflows.config import get_config


_EQUITY_SYSTEM_MESSAGE = (
    "You are a researcher tasked with analyzing fundamental information over the past week about a company. "
    "Please write a comprehensive report of the company's fundamental information such as financial documents, "
    "company profile, basic company financials, and company financial history to gain a full view of the "
    "company's fundamental information to inform traders. Make sure to include as much detail as possible. "
    "Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
    " Make sure to append a Markdown table at the end of the report to organize key points in the report, "
    "organized and easy to read."
    " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, "
    "`get_cashflow`, and `get_income_statement` for specific financial statements, `get_insider_transactions` "
    "for recent insider buying/selling activity, and `get_analyst_recommendations` for Wall Street analyst "
    "ratings and price targets."
)

_ETF_SYSTEM_MESSAGE = (
    "You are a researcher analyzing an ETF (exchange-traded fund) — a basket of securities, not an operating "
    "company. Write a comprehensive report covering: (1) fund profile (expense ratio, AUM, category, fund "
    "family, yield, NAV, inception); (2) top holdings and concentration risk (top-10 weight, single-name "
    "exposure); (3) sector / thematic allocation and tilts; (4) benchmark correlation and beta versus a "
    "relevant index (default SPY; use QQQ for tech-heavy ETFs, IWM for small caps, AGG for bonds, GLD for "
    "gold, etc.); and (5) implications for an investor — does this ETF add diversification, what risks does "
    "its construction carry, is the expense ratio competitive for its category. "
    "Do NOT discuss earnings, P/E, EPS, or insider transactions — they do not apply to ETFs. "
    "Provide specific, actionable insights with supporting evidence and append a Markdown summary table. "
    "Use the available tools: `get_etf_profile` for fund-level metrics, `get_etf_holdings` for constituents, "
    "`get_etf_sector_weights` for sector breakdown, `get_etf_correlation` to compare against a benchmark, "
    "and `get_analyst_recommendations` if applicable."
)


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        kind, _ = detect_instrument_kind(ticker)

        if kind == "etf":
            tools = [
                get_etf_profile,
                get_etf_holdings,
                get_etf_sector_weights,
                get_etf_correlation,
                get_analyst_recommendations,
            ]
            system_message = _ETF_SYSTEM_MESSAGE + get_language_instruction()
        else:
            tools = [
                get_fundamentals,
                get_balance_sheet,
                get_cashflow,
                get_income_statement,
                get_insider_transactions,
                get_analyst_recommendations,
            ]
            system_message = _EQUITY_SYSTEM_MESSAGE + get_language_instruction()

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
