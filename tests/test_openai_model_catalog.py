from unittest import mock

from cli.prompts import ask_openai_reasoning_effort
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import get_model_options


def _model_ids(mode: str) -> list[str]:
    return [model_id for _, model_id in get_model_options("openai", mode)]


def test_gpt_5_6_models_are_available_for_their_roles():
    quick_models = _model_ids("quick")
    deep_models = _model_ids("deep")

    assert {"gpt-5.6-luna", "gpt-5.6-terra"} <= set(quick_models)
    assert {"gpt-5.6-sol", "gpt-5.6-terra"} <= set(deep_models)
    assert "gpt-5.6-sol" not in quick_models
    assert "gpt-5.6-luna" not in deep_models
    assert "gpt-5.4" not in deep_models
    assert "gpt-5.2" not in deep_models


def test_current_openai_defaults_remain_available():
    assert DEFAULT_CONFIG["quick_think_llm"] in _model_ids("quick")
    assert DEFAULT_CONFIG["deep_think_llm"] in _model_ids("deep")


def test_openai_reasoning_effort_prompt_exposes_all_levels():
    prompt = mock.Mock()
    prompt.ask.return_value = "medium"

    with mock.patch("cli.prompts.questionary.select", return_value=prompt) as select:
        assert ask_openai_reasoning_effort() == "medium"

    choices = select.call_args.kwargs["choices"]
    assert [choice.value for choice in choices] == [
        "medium",
        "high",
        "low",
        "none",
        "xhigh",
        "max",
    ]
