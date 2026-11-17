from tradingagents.agents.rating import direction, extract_action, extract_rating
from tradingagents.agents.state import AgentState


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1, adaptive_extra_rounds=0):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.adaptive_extra_rounds = adaptive_extra_rounds

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""

        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # max_debate_rounds turns each for bull and bear
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        count = state["risk_debate_state"]["count"]
        if count >= 3 * (self.max_risk_discuss_rounds + self.adaptive_extra_rounds):
            return "Portfolio Manager"
        if count >= 3 * self.max_risk_discuss_rounds:
            research = extract_action(state.get("investment_plan", "")) or extract_rating(state.get("investment_plan", ""))
            trader = extract_action(state.get("trader_investment_plan", ""))
            if research is None or trader is None or direction(research) == direction(trader):
                return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
