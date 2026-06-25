import pytest

from scripts import dialectic_cost_calculator as calc
from src.config import ConfiguredModelSettings, DialecticLevelSettings, settings


def test_calculate_single_model_cost_uses_nested_model_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    levels = {
        "low": DialecticLevelSettings(
            MODEL_CONFIG=ConfiguredModelSettings(
                transport="anthropic",
                model="claude-haiku-4-5",
                thinking_budget_tokens=1024,
            ),
            MAX_TOOL_ITERATIONS=2,
        )
    }
    monkeypatch.setattr(settings.DIALECTIC, "LEVELS", levels)

    result = calc.calculate_level_cost("low", calc.TokenEstimates())

    assert result["two_phase"] is False
    assert result["provider"] == "anthropic"
    assert result["model"] == "claude-haiku-4-5"
    assert result["thinking_tokens"] == 1024


def test_calculate_two_phase_cost_uses_synthesis_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthesis = ConfiguredModelSettings(
        transport="anthropic",
        model="claude-opus-4-5",
        thinking_budget_tokens=1024,
        max_output_tokens=4096,
    )
    levels = {
        "max": DialecticLevelSettings(
            MODEL_CONFIG=ConfiguredModelSettings(
                transport="openai",
                model="z-ai/glm-4.7-flash",
            ),
            MAX_TOOL_ITERATIONS=2,
            SYNTHESIS_MODEL_CONFIG=synthesis,
        )
    }
    monkeypatch.setattr(settings.DIALECTIC, "LEVELS", levels)

    result = calc.calculate_level_cost("max", calc.TokenEstimates())

    assert result["two_phase"] is True
    assert result["model"] == "z-ai/glm-4.7-flash"
    assert result["synthesis_model"] == "claude-opus-4-5"
    assert result["synthesis_thinking_tokens"] == 1024
    assert result["synthesis_cost_realistic"] is not None
