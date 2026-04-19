from tradingagents.agents.utils.agent_utils import get_language_instruction


def create_investor_briefing(llm):
    """Translate the technical reports + final decision into plain English
    for a non-expert investor.

    Runs after the Portfolio Manager. Uses the quick-think LLM since the
    heavy reasoning has already happened upstream — this node is purely a
    translator/summarizer.
    """

    def investor_briefing_node(state) -> dict:
        ticker = state.get("company_of_interest", "")
        trade_date = state.get("trade_date", "")
        final_decision = state.get("final_trade_decision", "") or ""
        trader_plan = state.get("trader_investment_plan", "") or ""
        research_plan = state.get("investment_plan", "") or ""
        market_report = state.get("market_report", "") or ""
        sentiment_report = state.get("sentiment_report", "") or ""
        news_report = state.get("news_report", "") or ""
        fundamentals_report = state.get("fundamentals_report", "") or ""

        analyst_blocks = []
        if market_report:
            analyst_blocks.append(f"Market analyst said:\n{market_report}")
        if sentiment_report:
            analyst_blocks.append(f"Social sentiment analyst said:\n{sentiment_report}")
        if news_report:
            analyst_blocks.append(f"News analyst said:\n{news_report}")
        if fundamentals_report:
            analyst_blocks.append(f"Fundamentals analyst said:\n{fundamentals_report}")
        analyst_context = "\n\n---\n\n".join(analyst_blocks) if analyst_blocks else "(no analyst reports)"

        prompt = f"""You are writing a short, plain-English briefing for a regular investor who is NOT a finance professional. Imagine the reader has a brokerage account but does not know what RSI, MACD, EBITDA, "overweight", "free cash flow yield", "support level" or similar jargon mean. If you must use a technical term, immediately explain it in everyday words inside parentheses.

Aim for a reading level around grade 8. Keep sentences short. Be direct and concrete. No hedging filler like "it depends" or "investors may want to consider". Tell them what's going on and what to do.

The professional team has already finished their analysis. Your job is ONLY to translate their conclusion — do NOT second-guess it, contradict it, or invent new advice.

**Ticker**: {ticker}
**Date of analysis**: {trade_date}

**Final decision from the Portfolio Manager** (this is the source of truth — your "What To Do Today" section MUST match this):
{final_decision}

**Trader's plan** (concrete entry/exit ideas):
{trader_plan}

**Research team's plan**:
{research_plan}

**Underlying analyst reports**:
{analyst_context}

---

Produce the briefing in **exactly this markdown structure**, in this order, with these exact headings:

## Bottom Line
One or two sentences. State the rating in plain words (e.g. "The team thinks this stock is a strong buy", "The team says hold what you have, don't add", "The team says trim or sell"). Mention the company by ticker. No jargon.

## What To Do Today
A short bullet list (2–4 bullets) of concrete actions for the reader RIGHT NOW. Translate the rating to action verbs:
- Buy / Overweight → "Open a position" or "Add to your position", with the position-sizing hint from the trader's plan if available.
- Hold → "Sit tight — don't buy more, don't sell".
- Underweight / Sell → "Trim your position" or "Exit the position".
Always end this section with a single line in italics: *Underlying rating: <the exact rating word from the Portfolio Manager>.*

## What To Watch (Next Few Days)
A bullet list (3–5 bullets) of specific things the reader should keep an eye on over the coming days — earnings dates, news catalysts, price levels, sector events. Pull these from the analyst reports. For each bullet, briefly say WHY it matters in plain words.

## Plain-Language Risks
A bullet list (2–4 bullets) of the biggest things that could go wrong with this trade. Translate every risk into everyday language. Don't list generic risks ("the market could fall") — use the specific risks raised by the bear researcher and conservative analyst.

---

End the briefing with a single italic line:
*This is an AI-generated summary based on the team's analysis. It is not personalized financial advice.*

{get_language_instruction()}"""

        response = llm.invoke(prompt)

        return {
            "investor_briefing": response.content,
        }

    return investor_briefing_node
