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

    return render_template(
        settings.DIALECTIC.SYSTEM_PROMPT_TEMPLATE,
        {
            "peer_card_explanation": peer_card_explanation,
            "perspective_section": perspective_section,
        },
    )
