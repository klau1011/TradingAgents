"""Past outcome lessons reach each debating agent when available."""
from unittest.mock import MagicMock

import pytest

from tradingagents.agents import (
    create_aggressive_debator,
    create_bear_researcher,
    create_bull_researcher,
    create_conservative_debator,
    create_neutral_debator,
)


def _researcher_state(past_context=""):
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": "", "bull_history": "", "bear_history": "",
            "current_response": "", "count": 0,
        },
        "market_report": "Market report.",
        "sentiment_report": "Sentiment report.",
        "news_report": "News report.",
        "fundamentals_report": "Fundamentals report.",
        "past_context": past_context,
    }


def _risk_debator_state(past_context=""):
    return {
        "company_of_interest": "NVDA",
        "risk_debate_state": {
            "history": "", "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "current_aggressive_response": "",
            "current_conservative_response": "", "current_neutral_response": "",
            "count": 0,
        },
        "market_report": "Market report.",
        "sentiment_report": "Sentiment report.",
        "news_report": "News report.",
        "fundamentals_report": "Fundamentals report.",
        "trader_investment_plan": "Trader plan.",
        "past_context": past_context,
    }


_LESSONS_HEADER = "Past lessons from prior decisions and outcomes"
_INJECTION_AGENTS = [
    (create_bull_researcher, _researcher_state),
    (create_bear_researcher, _researcher_state),
    (create_aggressive_debator, _risk_debator_state),
    (create_conservative_debator, _risk_debator_state),
    (create_neutral_debator, _risk_debator_state),
]


@pytest.mark.unit
class TestPastContextInjection:

    @pytest.mark.parametrize(
        "factory,make_state", _INJECTION_AGENTS,
        ids=lambda x: getattr(x, "__name__", ""),
    )
    def test_lessons_block_present_iff_past_context(self, factory, make_state):
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="ok")
        node = factory(llm)

        node(make_state(past_context="[2026-01-05 | AAPL | Buy | +5.0% | +2.0% | 5d]\nGreat call."))
        prompt = llm.invoke.call_args[0][0]
        assert _LESSONS_HEADER in prompt
        assert "Great call." in prompt

        llm.invoke.reset_mock()
        node(make_state(past_context=""))
        prompt = llm.invoke.call_args[0][0]
        assert _LESSONS_HEADER not in prompt


@pytest.mark.unit
@pytest.mark.parametrize("past_context", ["", "An earlier call failed after weak evidence."])
def test_trader_receives_lessons_when_available(past_context):
    from tradingagents.agents.trader.trader import create_trader

    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError
    llm.invoke.return_value = MagicMock(content="**Action**: Hold")
    state = _risk_debator_state(past_context)
    state["investment_plan"] = "**Recommendation**: Hold"
    create_trader(llm)(state)
    prompt = str(llm.invoke.call_args[0][0])
    assert (_LESSONS_HEADER in prompt) == bool(past_context)
    if past_context:
        assert past_context in prompt
