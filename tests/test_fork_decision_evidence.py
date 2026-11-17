"""Fork decision metadata and original analyst evidence survive upstream integration."""
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, render_pm_decision
from tradingagents.agents.trader.trader import create_trader


@pytest.mark.unit
def test_pm_metadata_renders_without_losing_upstream_missing_fields():
    decision = PortfolioDecision(rating=PortfolioRating.OVERWEIGHT, executive_summary="s",
                                 investment_thesis="t", confidence="high",
                                 what_would_change_it="Buy on a guidance raise; Hold on a margin miss.")
    rendered = render_pm_decision(decision)
    assert "**Confidence**: high" in rendered
    assert decision.what_would_change_it in rendered
    assert "**Price Target**: not provided" in rendered


@pytest.mark.unit
@pytest.mark.parametrize("factory", [create_research_manager, create_trader])
def test_original_analyst_evidence_reaches_decision_makers(factory):
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError
    llm.invoke.return_value = MagicMock(content="**Rating**: Hold")
    factory(llm)({
        "company_of_interest": "NVDA", "investment_debate_state": {"count": 1},
        "investment_plan": "**Recommendation**: Hold", "market_report": "RSI 78.",
        "fundamentals_report": "Gross margin compressed 240bps QoQ.",
    })
    prompt = str(llm.invoke.call_args[0][0])
    assert "RSI 78." in prompt
    assert "Gross margin compressed 240bps QoQ." in prompt
