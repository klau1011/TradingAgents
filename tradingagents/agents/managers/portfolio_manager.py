"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext_with_object,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add — the bull thesis survived the strongest bear objection and a named catalyst with a timeline supports it
- **Overweight**: Favorable outlook that does not clear the Buy bar; gradually increase exposure
- **Hold**: Evidence genuinely balanced, or the deciding fact is missing; no action
- **Underweight**: Cautious outlook that does not clear the Sell bar; reduce exposure, take partial profits
- **Sell**: Strong conviction to exit or avoid — the bear thesis survived the strongest bull objection and a named catalyst with a timeline supports it

Buy and Sell are conviction calls and must clear that bar; Overweight and Underweight are the ordinary directional ratings. Hold is a legitimate answer when the deciding evidence is absent — but do not use it to dodge a side the evidence supports.

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts. State your confidence (low/medium/high) in the rating based on the strength of the evidence and how much the risk analysts agreed.

The risk analysts were each assigned a stance, so weigh the substance of their arguments rather than their conviction. Finally, name what would change this rating, using the two adjacent tiers that actually exist on the scale: for a middle rating give the development that would move it one tier more bullish and the one that would move it one tier more bearish; for Buy (nothing above it) give what would knock it down to Overweight and what would confirm holding it at Buy; for Sell (nothing below it) give what would lift it to Underweight and what would confirm holding it at Sell. Never name a tier outside Buy / Overweight / Hold / Underweight / Sell. Make each trigger concrete enough to check on a later re-analysis.{get_language_instruction()}"""

        final_trade_decision, decision_obj = invoke_structured_or_freetext_with_object(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
            "pm_decision": decision_obj.model_dump(mode="json") if decision_obj is not None else None,
        }

    return portfolio_manager_node
