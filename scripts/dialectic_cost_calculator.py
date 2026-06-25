#!/usr/bin/env python3
"""
Dialectic Cost Calculator

Calculates the maximum potential cost for each dialectic reasoning level based on
configured settings and model pricing.

Usage:
    uv run python scripts/dialectic_cost_calculator.py
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from src.config import REASONING_LEVELS, ReasoningLevel, settings  # noqa: E402

# Number of dialectic tools (from src/utils/agent_tools.py)
# Hardcoded to avoid circular import issues when importing from agent_tools
NUM_DIALECTIC_TOOLS = 7  # Full tool set for low/medium/high/max
NUM_DIALECTIC_TOOLS_MINIMAL = 2  # Minimal: only search_memory, search_messages
TOKENS_PER_TOOL = 350  # Approximate tokens per tool definition

# Prefetched observations: 25 explicit + 25 derived = ~2000 tokens (full)
# Minimal uses 10 + 10 = ~800 tokens
PREFETCH_OBSERVATIONS_FULL = 2_000
PREFETCH_OBSERVATIONS_MINIMAL = 800

# Target costs per reasoning level
TARGET_COSTS: dict[str, float] = {
    "minimal": 0.001,
    "low": 0.01,
    "medium": 0.05,
    "high": 0.10,
    "max": 0.50,
}

# Pricing per 1M tokens (as of January 2025)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.5-flash-lite": {
        "input": 0.10,
        "output": 0.40,
        "cached": 0.01,
    },
    "gemini-3-flash-preview": {
        "input": 0.50,
        "output": 3.00,
        "cached": 0.05,
    },
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cached": 0.10,
    },
    "claude-sonnet-4-5": {
        "input": 3.00,
        "output": 15.00,
        "cached": 0.30,
    },
    "claude-opus-4-5": {
        "input": 5.00,
        "output": 25.00,
        "cached": 0.50,
    },
    "z-ai/glm-4.7-flash": {
        "input": 0.07,
        "output": 0.40,
        "cached": 0.007,
    },
}

TEXT_SERIALIZATION_OVERHEAD = 1.20


@dataclass
class TokenEstimates:
    """Token estimates for different components.

    Default values are fallbacks; main() overrides most with actual config values.
    """

    # Fixed components (per request) - estimates, not from config
    system_prompt: int = 2_000  # ~2,000 tokens for agent system prompt
    num_tools: int = NUM_DIALECTIC_TOOLS  # Can be overridden for minimal
    peer_cards: int = 500  # Optional, enabled by default
    prefetched_observations: int = PREFETCH_OBSERVATIONS_FULL  # Can be overridden
    user_query: int = 200  # Assumption for typical query

    # Variable components - defaults from config
    session_history_max: int = settings.DIALECTIC.SESSION_HISTORY_MAX_TOKENS
    tool_result_per_iter: int = (
        settings.LLM.MAX_TOOL_OUTPUT_CHARS // 4
    )  # chars to tokens
    assistant_message_per_iter: int = 200  # Tool calls + reasoning

    # Output - from config
    max_output_tokens: int = settings.DIALECTIC.MAX_OUTPUT_TOKENS

    # Cap - from config
    max_input_tokens: int = settings.DIALECTIC.MAX_INPUT_TOKENS

    # Realistic output estimates (tool calls are small, only final answer is large)
    realistic_tool_call_output: int = 150  # JSON for tool_use block
    realistic_thinking_per_tool: int = (
        400  # Models don't use full budget for tool decisions
    )
    realistic_final_answer: int = 1_500  # Final response to user

    @property
    def tool_definitions(self) -> int:
        """Tokens for tool definitions based on num_tools."""
        return self.num_tools * TOKENS_PER_TOOL

    @property
    def first_iteration_input(self) -> int:
        """Total input tokens for first iteration (all fresh)."""
        return (
            self.system_prompt
            + self.tool_definitions
            + self.peer_cards
            + self.session_history_max
            + self.prefetched_observations
            + self.user_query
        )

    @property
    def cacheable_tokens(self) -> int:
        """Tokens that can be cached across iterations (system + tools)."""
        return self.system_prompt + self.tool_definitions

    def subsequent_iteration_growth(self) -> int:
        """Additional tokens per subsequent iteration."""
        return self.tool_result_per_iter + self.assistant_message_per_iter


def calculate_single_model_cost(
    level_name: ReasoningLevel,
    base_estimates: TokenEstimates,
) -> dict[str, Any]:
    """
    Calculate the maximum potential cost for a single-model reasoning level.

    Returns dict with all cost components, including both worst-case and realistic estimates.
    """
    level_config = settings.DIALECTIC.LEVELS[level_name]
    model_config = level_config.MODEL_CONFIG

    # Use minimal tools, reduced prefetch, and reduced output for minimal reasoning
    is_minimal = level_name == "minimal"
    num_tools = NUM_DIALECTIC_TOOLS_MINIMAL if is_minimal else NUM_DIALECTIC_TOOLS
    prefetch = (
        PREFETCH_OBSERVATIONS_MINIMAL if is_minimal else PREFETCH_OBSERVATIONS_FULL
    )
    # Get max_output_tokens from level config, fall back to global default
    max_output = (
        level_config.MAX_OUTPUT_TOKENS
        if level_config.MAX_OUTPUT_TOKENS is not None
        else base_estimates.max_output_tokens
    )
    # Realistic final answer is capped at max output
    realistic_final = min(max_output, base_estimates.realistic_final_answer)
    estimates = TokenEstimates(
        system_prompt=base_estimates.system_prompt,
        num_tools=num_tools,
        peer_cards=base_estimates.peer_cards,
        prefetched_observations=prefetch,
        user_query=base_estimates.user_query,
        session_history_max=base_estimates.session_history_max,
        tool_result_per_iter=base_estimates.tool_result_per_iter,
        assistant_message_per_iter=base_estimates.assistant_message_per_iter,
        max_output_tokens=max_output,
        max_input_tokens=base_estimates.max_input_tokens,
        realistic_tool_call_output=base_estimates.realistic_tool_call_output,
        realistic_thinking_per_tool=base_estimates.realistic_thinking_per_tool,
        realistic_final_answer=realistic_final,
    )

    model = model_config.model
    max_iterations = level_config.MAX_TOOL_ITERATIONS
    thinking_budget = model_config.thinking_budget_tokens or 0
    provider = model_config.transport

    # Get pricing for this model
    pricing = MODEL_PRICING.get(model, {"input": 0, "output": 0, "cached": 0})

    # Calculate input tokens per iteration
    first_iter_input = min(estimates.first_iteration_input, estimates.max_input_tokens)
    cacheable = estimates.cacheable_tokens
    growth_per_iter = estimates.subsequent_iteration_growth()

    # === WORST-CASE OUTPUT CALCULATION ===
    # Assumes max output on every iteration (very conservative)
    output_per_iter_worst = thinking_budget + estimates.max_output_tokens

    # === REALISTIC OUTPUT CALCULATION ===
    # Tool-calling iterations: small JSON output + partial thinking usage
    # Final iteration: full thinking budget + actual response
    realistic_thinking_per_tool = min(
        estimates.realistic_thinking_per_tool, thinking_budget
    )
    tool_iter_output = (
        realistic_thinking_per_tool + estimates.realistic_tool_call_output
    )
    final_iter_output = thinking_budget + estimates.realistic_final_answer

    # Calculate costs across all iterations
    # First iteration: 100% uncached
    # Subsequent iterations: ~90% cache hit on system+tools
    cache_hit_rate = 0.90

    total_input_tokens = 0
    total_cached_tokens = 0
    total_uncached_tokens = 0
    total_output_tokens_worst = 0
    total_output_tokens_realistic = 0

    for i in range(max_iterations):
        if i == 0:
            # First iteration: all fresh
            iter_input = first_iter_input
            cached = 0
            uncached = iter_input
        else:
            # Subsequent iterations: accumulated context + growth
            iter_input = min(
                first_iter_input + (i * growth_per_iter), estimates.max_input_tokens
            )
            cached = int(cacheable * cache_hit_rate)
            uncached = iter_input - cached

        total_input_tokens += iter_input
        total_cached_tokens += cached
        total_uncached_tokens += uncached

        # Worst-case: max output every iteration
        total_output_tokens_worst += output_per_iter_worst

        # Realistic: tool calls are small, only final iteration has full response
        is_final = i == max_iterations - 1
        total_output_tokens_realistic += (
            final_iter_output if is_final else tool_iter_output
        )

    # Calculate worst-case costs (per 1M tokens)
    input_cost = (total_uncached_tokens / 1_000_000) * pricing["input"]
    cached_cost = (total_cached_tokens / 1_000_000) * pricing["cached"]
    output_cost_worst = (total_output_tokens_worst / 1_000_000) * pricing["output"]
    total_cost_worst = input_cost + cached_cost + output_cost_worst

    # Calculate realistic costs
    output_cost_realistic = (total_output_tokens_realistic / 1_000_000) * pricing[
        "output"
    ]
    total_cost_realistic = input_cost + cached_cost + output_cost_realistic

    return {
        "level": level_name,
        "two_phase": False,
        "provider": provider,
        "model": model,
        "synthesis_provider": None,
        "synthesis_model": None,
        "max_iterations": max_iterations,
        "thinking_tokens": thinking_budget,
        "synthesis_thinking_tokens": 0,
        "first_iter_input": first_iter_input,
        "total_input_tokens": total_input_tokens,
        "total_cached_tokens": total_cached_tokens,
        "total_uncached_tokens": total_uncached_tokens,
        # Worst-case output
        "total_output_tokens": total_output_tokens_worst,
        "output_cost": output_cost_worst,
        "total_cost": total_cost_worst,
        # Realistic output
        "total_output_tokens_realistic": total_output_tokens_realistic,
        "output_cost_realistic": output_cost_realistic,
        "total_cost_realistic": total_cost_realistic,
        # Shared input costs
        "input_cost": input_cost,
        "cached_cost": cached_cost,
        "search_cost_realistic": None,
        "synthesis_cost_realistic": None,
    }


def calculate_two_phase_cost(
    level_name: ReasoningLevel,
    base_estimates: TokenEstimates,
) -> dict[str, Any]:
    """Calculate cost for search-model + synthesis-model dialectic."""
    level_config = settings.DIALECTIC.LEVELS[level_name]
    search_config = level_config.MODEL_CONFIG
    synthesis_config = level_config.SYNTHESIS_MODEL_CONFIG
    if synthesis_config is None:
        raise ValueError("calculate_two_phase_cost requires synthesis config")

    search_max_output = level_config.MAX_OUTPUT_TOKENS or 1024
    synthesis_max_output = (
        synthesis_config.max_output_tokens
        if synthesis_config.max_output_tokens is not None
        else base_estimates.max_output_tokens
    )

    estimates = TokenEstimates(
        system_prompt=base_estimates.system_prompt,
        num_tools=NUM_DIALECTIC_TOOLS,
        peer_cards=base_estimates.peer_cards,
        prefetched_observations=PREFETCH_OBSERVATIONS_FULL,
        user_query=base_estimates.user_query,
        session_history_max=base_estimates.session_history_max,
        tool_result_per_iter=base_estimates.tool_result_per_iter,
        assistant_message_per_iter=base_estimates.assistant_message_per_iter,
        max_output_tokens=synthesis_max_output,
        max_input_tokens=base_estimates.max_input_tokens,
        realistic_tool_call_output=base_estimates.realistic_tool_call_output,
        realistic_thinking_per_tool=base_estimates.realistic_thinking_per_tool,
        realistic_final_answer=min(
            synthesis_max_output, base_estimates.realistic_final_answer
        ),
    )

    search_pricing = MODEL_PRICING.get(
        search_config.model, {"input": 0, "output": 0, "cached": 0}
    )
    synthesis_pricing = MODEL_PRICING.get(
        synthesis_config.model, {"input": 0, "output": 0, "cached": 0}
    )
    search_thinking = search_config.thinking_budget_tokens or 0
    synthesis_thinking = synthesis_config.thinking_budget_tokens or 0
    max_iterations = level_config.MAX_TOOL_ITERATIONS

    first_iter_input = min(estimates.first_iteration_input, estimates.max_input_tokens)
    cacheable = estimates.cacheable_tokens
    growth_per_iter = estimates.subsequent_iteration_growth()
    cache_hit_rate = 0.90

    search_total_input = 0
    search_total_cached = 0
    search_total_uncached = 0
    search_total_output_worst = 0
    search_total_output_realistic = 0

    realistic_thinking_per_tool = min(
        estimates.realistic_thinking_per_tool, search_thinking
    )
    tool_iter_output = (
        realistic_thinking_per_tool + estimates.realistic_tool_call_output
    )
    search_output_per_iter_worst = search_thinking + search_max_output

    for i in range(max_iterations):
        if i == 0:
            iter_input = first_iter_input
            cached = 0
            uncached = iter_input
        else:
            iter_input = min(
                first_iter_input + (i * growth_per_iter), estimates.max_input_tokens
            )
            cached = int(cacheable * cache_hit_rate)
            uncached = iter_input - cached

        search_total_input += iter_input
        search_total_cached += cached
        search_total_uncached += uncached
        search_total_output_worst += search_output_per_iter_worst
        search_total_output_realistic += tool_iter_output

    search_input_cost = (search_total_uncached / 1_000_000) * search_pricing["input"]
    search_cached_cost = (search_total_cached / 1_000_000) * search_pricing["cached"]
    search_output_cost_worst = (
        search_total_output_worst / 1_000_000
    ) * search_pricing["output"]
    search_output_cost_realistic = (
        search_total_output_realistic / 1_000_000
    ) * search_pricing["output"]
    search_cost_worst = (
        search_input_cost + search_cached_cost + search_output_cost_worst
    )
    search_cost_realistic = (
        search_input_cost + search_cached_cost + search_output_cost_realistic
    )

    search_conversation_tokens = max_iterations * growth_per_iter
    serialized_search_tokens = int(
        search_conversation_tokens * TEXT_SERIALIZATION_OVERHEAD
    )
    synthesis_instruction_tokens = 100
    synthesis_input = min(
        estimates.system_prompt
        + estimates.peer_cards
        + estimates.session_history_max
        + estimates.prefetched_observations
        + estimates.user_query
        + serialized_search_tokens
        + synthesis_instruction_tokens,
        estimates.max_input_tokens,
    )
    synthesis_output_worst = synthesis_thinking + synthesis_max_output
    synthesis_output_realistic = synthesis_thinking + estimates.realistic_final_answer
    synthesis_input_cost = (
        synthesis_input / 1_000_000
    ) * synthesis_pricing["input"]
    synthesis_output_cost_worst = (
        synthesis_output_worst / 1_000_000
    ) * synthesis_pricing["output"]
    synthesis_output_cost_realistic = (
        synthesis_output_realistic / 1_000_000
    ) * synthesis_pricing["output"]
    synthesis_cost_worst = synthesis_input_cost + synthesis_output_cost_worst
    synthesis_cost_realistic = synthesis_input_cost + synthesis_output_cost_realistic

    total_input_tokens = search_total_input + synthesis_input
    total_output_tokens_worst = search_total_output_worst + synthesis_output_worst
    total_output_tokens_realistic = (
        search_total_output_realistic + synthesis_output_realistic
    )
    total_cost_worst = search_cost_worst + synthesis_cost_worst
    total_cost_realistic = search_cost_realistic + synthesis_cost_realistic

    return {
        "level": level_name,
        "two_phase": True,
        "provider": search_config.transport,
        "model": search_config.model,
        "synthesis_provider": synthesis_config.transport,
        "synthesis_model": synthesis_config.model,
        "max_iterations": max_iterations,
        "thinking_tokens": search_thinking,
        "synthesis_thinking_tokens": synthesis_thinking,
        "first_iter_input": first_iter_input,
        "total_input_tokens": total_input_tokens,
        "total_cached_tokens": search_total_cached,
        "total_uncached_tokens": search_total_uncached + synthesis_input,
        "total_output_tokens": total_output_tokens_worst,
        "output_cost": search_output_cost_worst + synthesis_output_cost_worst,
        "total_cost": total_cost_worst,
        "total_output_tokens_realistic": total_output_tokens_realistic,
        "output_cost_realistic": (
            search_output_cost_realistic + synthesis_output_cost_realistic
        ),
        "total_cost_realistic": total_cost_realistic,
        "input_cost": search_input_cost + synthesis_input_cost,
        "cached_cost": search_cached_cost,
        "search_cost_realistic": search_cost_realistic,
        "synthesis_cost_realistic": synthesis_cost_realistic,
        "synthesis_input_tokens": synthesis_input,
        "synthesis_output_tokens_realistic": synthesis_output_realistic,
    }


def calculate_level_cost(
    level_name: ReasoningLevel,
    base_estimates: TokenEstimates,
) -> dict[str, Any]:
    """Calculate level cost, auto-detecting optional two-phase config."""
    level_config = settings.DIALECTIC.LEVELS[level_name]
    if level_name != "minimal" and level_config.SYNTHESIS_MODEL_CONFIG is not None:
        return calculate_two_phase_cost(level_name, base_estimates)
    return calculate_single_model_cost(level_name, base_estimates)


def main():
    console = Console()

    # TokenEstimates defaults are already sourced from config
    estimates = TokenEstimates()

    console.print("\n[bold]Dialectic Cost Calculator[/bold]\n")

    # Print assumptions
    console.print("[dim]Token Estimates:[/dim]")
    console.print(f"  System prompt: {estimates.system_prompt:,} tokens")
    console.print(
        f"  Tool definitions (full: {NUM_DIALECTIC_TOOLS} tools): {estimates.tool_definitions:,} tokens"
    )
    console.print(
        f"  Tool definitions (minimal: {NUM_DIALECTIC_TOOLS_MINIMAL} tools): {NUM_DIALECTIC_TOOLS_MINIMAL * TOKENS_PER_TOOL:,} tokens"
    )
    console.print(f"  Peer cards: {estimates.peer_cards:,} tokens")
    console.print(f"  Session history (max): {estimates.session_history_max:,} tokens")
    console.print(
        f"  Prefetched observations (full: 25+25): {PREFETCH_OBSERVATIONS_FULL:,} tokens"
    )
    console.print(
        f"  Prefetched observations (minimal: 10+10): {PREFETCH_OBSERVATIONS_MINIMAL:,} tokens"
    )
    console.print(f"  User query: {estimates.user_query:,} tokens")
    console.print(
        f"  Tool result per iteration: {estimates.tool_result_per_iter:,} tokens"
    )
    console.print(
        f"  Max output tokens (default): {estimates.max_output_tokens:,} tokens"
    )
    minimal_max_output = settings.DIALECTIC.LEVELS["minimal"].MAX_OUTPUT_TOKENS
    if minimal_max_output is not None:
        console.print(
            f"  Max output tokens (minimal override): {minimal_max_output:,} tokens"
        )
    console.print(f"  Max input tokens (cap): {estimates.max_input_tokens:,} tokens")
    console.print(
        f"  First iteration input: {estimates.first_iteration_input:,} tokens"
    )
    console.print()
    console.print("[dim]Realistic Output Estimates:[/dim]")
    console.print(
        f"  Tool call output: {estimates.realistic_tool_call_output:,} tokens (JSON for tool_use)"
    )
    console.print(
        f"  Thinking per tool call: {estimates.realistic_thinking_per_tool:,} tokens (partial budget use)"
    )
    console.print(
        f"  Final answer: {estimates.realistic_final_answer:,} tokens (actual response)"
    )
    console.print()

    # Calculate costs for each level (from config.REASONING_LEVELS)
    results = [calculate_level_cost(level, estimates) for level in REASONING_LEVELS]

    # Create summary table
    table = Table(title="Cost by Reasoning Level", show_lines=True)
    table.add_column("Level", style="cyan", no_wrap=True)
    table.add_column("Mode", style="dim", no_wrap=True)
    table.add_column("Model", style="dim", no_wrap=True)
    table.add_column("Synthesis", style="dim", no_wrap=True)
    table.add_column("Iters", justify="right")
    table.add_column("Think", justify="right")
    table.add_column("Target", justify="right", style="dim")
    table.add_column("Realistic", justify="right", style="bold green")
    table.add_column("Worst Case", justify="right", style="yellow")

    for r in results:
        table.add_row(
            r["level"],
            "2-phase" if r["two_phase"] else "single",
            r["model"],
            r.get("synthesis_model") or "-",
            str(r["max_iterations"]),
            f"{r['thinking_tokens']:,}",
            f"${TARGET_COSTS.get(r['level'], 0):.3f}",
            f"${r['total_cost_realistic']:.4f}",
            f"${r['total_cost']:.4f}",
        )

    console.print(table)

    # Detailed cost breakdown table
    console.print()
    detail_table = Table(
        title="Cost Breakdown by Component (Realistic)", show_lines=True
    )
    detail_table.add_column("Level", style="cyan", no_wrap=True)
    detail_table.add_column("Input $", justify="right")
    detail_table.add_column("Cached $", justify="right", style="dim")
    detail_table.add_column("Output $", justify="right")
    detail_table.add_column("Search $", justify="right", style="dim")
    detail_table.add_column("Synthesis $", justify="right", style="dim")
    detail_table.add_column("Total $", justify="right", style="bold green")

    for r in results:
        detail_table.add_row(
            r["level"],
            f"${r['input_cost']:.4f}",
            f"${r['cached_cost']:.4f}",
            f"${r['output_cost_realistic']:.4f}",
            (
                f"${r['search_cost_realistic']:.4f}"
                if r.get("search_cost_realistic") is not None
                else "-"
            ),
            (
                f"${r['synthesis_cost_realistic']:.4f}"
                if r.get("synthesis_cost_realistic") is not None
                else "-"
            ),
            f"${r['total_cost_realistic']:.4f}",
        )

    console.print(detail_table)

    # Print detailed breakdown for max level
    console.print("\n[bold]Detailed Breakdown for 'max' Level:[/bold]")
    max_result = results[-1]
    console.print(f"  Model: {max_result['model']} ({max_result['provider']})")
    if max_result["two_phase"]:
        console.print(
            "  Synthesis model: "
            + f"{max_result['synthesis_model']} "
            + f"({max_result['synthesis_provider']})"
        )
    console.print(f"  Max iterations: {max_result['max_iterations']}")
    console.print(f"  Thinking budget per iteration: {max_result['thinking_tokens']:,}")
    if max_result["two_phase"]:
        console.print(
            "  Synthesis thinking budget: "
            + f"{max_result['synthesis_thinking_tokens']:,}"
        )
    console.print(f"  First iteration input: {max_result['first_iter_input']:,} tokens")
    console.print(
        f"  Total input tokens (all iterations): {max_result['total_input_tokens']:,}"
    )
    max_pricing = MODEL_PRICING.get(
        max_result["model"], {"input": 0, "output": 0, "cached": 0}
    )
    console.print(
        f"    - Uncached: {max_result['total_uncached_tokens']:,} "
        + f"@ ${max_pricing['input']}/1M"
    )
    console.print(
        f"    - Cached: {max_result['total_cached_tokens']:,} "
        + f"@ ${max_pricing['cached']}/1M"
    )
    console.print("  Output tokens:")
    console.print(
        f"    - Realistic: {max_result['total_output_tokens_realistic']:,} "
        + f"(9 tool calls × {estimates.realistic_thinking_per_tool + estimates.realistic_tool_call_output} + final {max_result['thinking_tokens'] + estimates.realistic_final_answer})"
    )
    console.print(
        f"    - Worst case: {max_result['total_output_tokens']:,} "
        + f"(10 × {max_result['thinking_tokens'] + estimates.max_output_tokens})"
    )
    console.print(
        f"    - Output rate: ${max_pricing['output']}/1M"
    )
    console.print(
        f"\n  [bold green]Realistic cost: ${max_result['total_cost_realistic']:.4f}[/bold green]"
    )
    console.print(
        f"  [yellow]Worst case cost: ${max_result['total_cost']:.4f}[/yellow]"
    )

    # Print pricing table
    console.print("\n[dim]Model Pricing ($/1M tokens):[/dim]")
    pricing_table = Table(show_header=True, header_style="dim")
    pricing_table.add_column("Model")
    pricing_table.add_column("Input", justify="right")
    pricing_table.add_column("Output", justify="right")
    pricing_table.add_column("Cached", justify="right")

    for model, prices in MODEL_PRICING.items():
        pricing_table.add_row(
            model,
            f"${prices['input']:.2f}",
            f"${prices['output']:.2f}",
            f"${prices['cached']:.2f}",
        )

    console.print(pricing_table)

    console.print(
        "\n[dim]Note: 'Realistic' assumes tool calls use ~550 output tokens each "
        + "(400 thinking + 150 JSON), with full budget only on final answer.\n"
        + "'Worst case' assumes max output tokens on every iteration. "
        + "Actual costs may be even lower due to early termination.[/dim]\n"
    )


if __name__ == "__main__":
    main()
