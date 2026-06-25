from jinja2.exceptions import TemplateNotFound

from src.deriver.prompts import minimal_deriver_prompt
from src.dialectic.prompts import agent_system_prompt
from src.utils.templates import get_template_manager, render_template


def test_template_manager_singleton() -> None:
    assert get_template_manager() is get_template_manager()


def test_render_missing_template_raises_template_not_found() -> None:
    try:
        render_template("missing/template.jinja", {})
    except TemplateNotFound as exc:
        assert exc.name == "missing/template.jinja"
    else:
        raise AssertionError("expected TemplateNotFound")


def test_minimal_deriver_prompt_renders_custom_instructions() -> None:
    prompt = minimal_deriver_prompt(
        peer_id="alice",
        messages="alice: I moved to Boston.",
        custom_instructions="Prefer concrete timeline facts.",
    )

    assert "CUSTOM INSTRUCTIONS:" in prompt
    assert "Prefer concrete timeline facts." in prompt
    assert "Target peer:\nalice" in prompt
    assert "alice: I moved to Boston." in prompt


def test_minimal_deriver_prompt_omits_empty_custom_instructions() -> None:
    prompt = minimal_deriver_prompt(
        peer_id="alice",
        messages="alice: hello",
        custom_instructions="   ",
    )

    assert "CUSTOM INSTRUCTIONS:" not in prompt


def test_agent_system_prompt_renders_peer_card_sections() -> None:
    prompt = agent_system_prompt(
        observer="alice",
        observed="bob",
        observer_peer_card=["alice prefers concise answers"],
        observed_peer_card=["bob works in robotics"],
    )

    assert "alice's understanding of bob" in prompt
    assert "alice prefers concise answers" in prompt
    assert "bob works in robotics" in prompt
    assert "AVAILABLE TOOLS" in prompt
