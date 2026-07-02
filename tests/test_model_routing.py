"""Tests for PR 4: per-stage model routing and the adaptive risk debate."""

from unittest.mock import MagicMock

import pytest

from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import LLM_MAP_STAGES, GraphSetup

# ---------------------------------------------------------------------------
# Per-stage LLM map
# ---------------------------------------------------------------------------


def _make_setup(llm_map=None):
    quick, deep = MagicMock(name="quick"), MagicMock(name="deep")
    setup = GraphSetup(quick, deep, {}, ConditionalLogic(), llm_map=llm_map)
    return setup, quick, deep


@pytest.mark.unit
class TestAgentLlmMap:
    def test_empty_map_returns_defaults(self):
        setup, quick, deep = _make_setup()
        for stage in LLM_MAP_STAGES:
            assert setup._llm(stage, quick) is quick
            assert setup._llm(stage, deep) is deep

    def test_map_overrides_single_stage(self):
        setup, quick, deep = _make_setup({"research_manager": "quick"})
        assert setup._llm("research_manager", deep) is quick
        assert setup._llm("portfolio_manager", deep) is deep
        assert setup._llm("analysts", quick) is quick

    def test_deep_override(self):
        setup, quick, deep = _make_setup({"risk_analysts": "deep"})
        assert setup._llm("risk_analysts", quick) is deep

    def test_unknown_stage_raises(self):
        with pytest.raises(ValueError, match="unknown stage"):
            _make_setup({"trader_agent": "quick"})

    def test_unknown_value_raises(self):
        with pytest.raises(ValueError, match="'quick' or 'deep'"):
            _make_setup({"trader": "gpt-5.5"})


# ---------------------------------------------------------------------------
# Adaptive risk debate
# ---------------------------------------------------------------------------

AGREE_PLAN = "**Recommendation**: Buy\n\n**Rationale**: Strong setup."
AGREE_TRADER = "**Action**: Buy\n\nFINAL TRANSACTION PROPOSAL: **BUY**"
DISAGREE_TRADER = "**Action**: Sell\n\nFINAL TRANSACTION PROPOSAL: **SELL**"


def _risk_state(count, investment_plan=AGREE_PLAN, trader_plan=AGREE_TRADER,
                latest_speaker="Neutral"):
    return {
        "risk_debate_state": {"count": count, "latest_speaker": latest_speaker},
        "investment_plan": investment_plan,
        "trader_investment_plan": trader_plan,
    }


@pytest.mark.unit
class TestAdaptiveRiskDebate:
    def test_default_zero_stops_at_base_cap_even_on_disagreement(self):
        logic = ConditionalLogic(max_risk_discuss_rounds=1)
        state = _risk_state(3, trader_plan=DISAGREE_TRADER)
        assert logic.should_continue_risk_analysis(state) == "Portfolio Manager"

    def test_agreement_stops_at_base_cap_despite_extra_rounds(self):
        logic = ConditionalLogic(max_risk_discuss_rounds=1, adaptive_extra_rounds=2)
        state = _risk_state(3)
        assert logic.should_continue_risk_analysis(state) == "Portfolio Manager"

    def test_disagreement_runs_exactly_n_extra_cycles(self):
        logic = ConditionalLogic(max_risk_discuss_rounds=1, adaptive_extra_rounds=2)
        # Past the base cap (3) but under the hard cap (9): keeps debating.
        for count in range(3, 9):
            state = _risk_state(count, trader_plan=DISAGREE_TRADER)
            assert logic.should_continue_risk_analysis(state) != "Portfolio Manager"
        # At the hard cap: stops regardless of disagreement.
        state = _risk_state(9, trader_plan=DISAGREE_TRADER)
        assert logic.should_continue_risk_analysis(state) == "Portfolio Manager"

    def test_speaker_rotation_below_cap_unchanged(self):
        logic = ConditionalLogic(max_risk_discuss_rounds=1, adaptive_extra_rounds=2)
        cases = {
            "Aggressive": "Conservative Analyst",
            "Conservative": "Neutral Analyst",
            "Neutral": "Aggressive Analyst",
        }
        for speaker, expected in cases.items():
            state = _risk_state(1, latest_speaker=speaker)
            assert logic.should_continue_risk_analysis(state) == expected
        # Rotation also holds in the adaptive window while disagreeing.
        state = _risk_state(4, trader_plan=DISAGREE_TRADER, latest_speaker="Aggressive")
        assert logic.should_continue_risk_analysis(state) == "Conservative Analyst"

    def test_hold_vs_hold_counts_as_agreement(self):
        logic = ConditionalLogic(max_risk_discuss_rounds=1, adaptive_extra_rounds=2)
        state = _risk_state(
            3,
            investment_plan="**Recommendation**: Hold",
            trader_plan="**Action**: Hold",
        )
        assert logic.should_continue_risk_analysis(state) == "Portfolio Manager"
