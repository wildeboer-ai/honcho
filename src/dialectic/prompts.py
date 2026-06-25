"""
System prompts for the Dialectic Agent.
"""

from src.config import settings
from src.utils.templates import render_template


def agent_system_prompt(
    observer: str,
    observed: str,
    observer_peer_card: list[str] | None,
    observed_peer_card: list[str] | None,
    custom_rules: str = "",
) -> str:
    """
    Generate the agent system prompt for the dialectic agent.

    Args:
        observer: The peer making the query
        observed: The peer being queried about
        observer_peer_card: Biographical information about the observer
        observed_peer_card: Biographical information about the observed peer

    Returns:
        Formatted system prompt string for the agent
    """
    # Determine if we have any peer card data
    peer_cards_enabled = (
        observer_peer_card is not None or observed_peer_card is not None
    )
    # Build peer card sections
    if observer != observed:
        # Directional query: observer asking about observed
        observer_card_section = ""
        if observer_peer_card:
            observer_card_section = f"""
Known biographical information about {observer} (the one asking):
<observer_peer_card>
{chr(10).join(observer_peer_card)}
</observer_peer_card>
"""

        observed_card_section = ""
        if observed_peer_card:
            observed_card_section = f"""
Known biographical information about {observed} (the subject):
<observed_peer_card>
{chr(10).join(observed_peer_card)}
</observed_peer_card>
"""

        perspective_section = f"""
You are answering queries from the perspective of {observer}'s understanding of {observed}.
This is a directional query - {observer} wants to know about {observed}.

{observer_card_section}
{observed_card_section}
"""
    else:
        # Global query: omniscient view of the peer
        peer_card_section = ""
        if observer_peer_card:
            peer_card_section = f"""
Known biographical information about {observed}:
<peer_card>
{chr(10).join(observer_peer_card)}
</peer_card>
"""

        perspective_section = f"""
You are answering queries about '{observed}'.

{peer_card_section}
"""

    # Build peer card explanation section (only if peer cards are being used)
    peer_card_explanation = ""
    if peer_cards_enabled:
        peer_card_explanation = """
Peer cards are **constructed summaries** - they are synthesized from the same observations stored in memory. This means:
- Information in a peer card originates from observations you can also find via `search_memory`
- The peer card is a convenience summary, not a separate source of truth
"""

    prompt = render_template(
        settings.DIALECTIC.SYSTEM_PROMPT_TEMPLATE,
        {
            "peer_card_explanation": peer_card_explanation,
            "perspective_section": perspective_section,
        },
    )
    if custom_rules.strip():
        prompt += f"""

## ADDITIONAL GUIDELINES (workspace-specific)

{custom_rules.strip()}
"""
    return prompt


def workspace_agent_system_prompt() -> str:
    """Generate the system prompt for workspace-level dialectic queries."""
    return """
You are a workspace-level analysis agent that can query memory across all peers in this workspace. You synthesize information from peer representations, peer cards, and conversation history.

Unlike a peer-level agent that focuses on one observer/observed pair, you must discover relevant peers and then query the specific peer relationships that can answer the question.

## AVAILABLE TOOLS

Discovery tools:
- `get_workspace_stats`: Get peer, session, message counts, and date range.
- `get_active_peers`: Get peers ranked by recent activity or message count.

Memory tools:
- `search_memory`: Semantic search within a specific peer representation. You must specify `observer` and `observed`. For a peer's global representation, set observer and observed to the same peer name.
- `get_peer_card`: Get a peer-card summary for a specific observer/observed pair.
- `get_reasoning_chain`: Traverse the reasoning tree for an observation.

Conversation tools:
- `search_messages`: Semantic search over messages across the workspace or scoped session.
- `grep_messages`: Exact text search across messages.
- `get_observation_context`: Get messages surrounding specific observation message IDs.
- `get_messages_by_date_range`: Get messages within a time period.
- `search_messages_temporal`: Semantic search with date filtering.

## WORKFLOW

1. Orient yourself with the workspace overview already provided in the query context. Use `get_active_peers` when you need to discover likely peers.
2. Discover relevant peers through message search when the query does not name them. Message results include peer names.
3. Drill into specific peer representations with `search_memory(observer=peer, observed=peer, query=...)`.
4. Use different observer/observed values only when asking about one peer's specific understanding of another peer.
5. Attribute information to the peer or peer relationship it came from.
6. For cross-peer patterns, compare findings explicitly and note both similarities and differences.
7. If the memory system does not contain the requested information, say that directly. Do not guess.

Never fabricate information. Do not explain tool usage; provide the synthesized answer.
"""
