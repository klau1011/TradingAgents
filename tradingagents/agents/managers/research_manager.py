"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import (
    get_analyst_reports_from_state,
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        history = state["investment_debate_state"].get("history", "")
        analyst_reports = get_analyst_reports_from_state(state)

        past_context = state.get("past_context", "")
        lessons_block = (
            f"\n\n**Lessons from prior decisions and outcomes:**\n{past_context}"
            if past_context
            else ""
        )

        investment_debate_state = state["investment_debate_state"]

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: The bull thesis survives the bear's single strongest objection, and there is a named catalyst with a timeline
- **Overweight**: Constructive lean that does not clear the Buy bar; recommend gradually increasing exposure
- **Hold**: The evidence is genuinely balanced, or the fact that would decide it is missing
- **Underweight**: Cautious lean that does not clear the Sell bar; recommend trimming exposure
- **Sell**: The bear thesis survives the bull's single strongest objection, and there is a named catalyst with a timeline

Buy and Sell are conviction calls and must clear that bar — do not reach for them to sound decisive. Overweight and Underweight are the ordinary directional ratings. Hold is a real answer when the deciding evidence is absent; do not use it to avoid taking a side the evidence supports.

---

The debate below is advocacy: each researcher was assigned a side and argues it. Weigh it for the quality of the reasoning, not for who sounded more confident. Verify factual claims against the analyst reports, which are the primary evidence — where a researcher's claim conflicts with a report, the report wins. If a material fact in the reports went unmentioned by both sides, raise it yourself and account for it.

**Analyst Reports (primary evidence):**
{analyst_reports}

---

**Debate History:**
{history}{lessons_block}""" + get_language_instruction()

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
