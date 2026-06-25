"""API route constants for Honcho SDK."""

API_VERSION = "v3"


# Workspace routes
def workspaces() -> str:
    return f"/{API_VERSION}/workspaces"


def workspaces_list() -> str:
    return f"/{API_VERSION}/workspaces/list"


def workspace(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}"


def workspace_search(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/search"


def workspace_chat(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/chat"


def workspace_queue_status(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/queue/status"


def workspace_schedule_dream(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/schedule_dream"


# Peer routes
def peers(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/peers"


def peers_list(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/peers/list"


def peer(workspace_id: str, peer_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/peers/{peer_id}"


def peer_chat(workspace_id: str, peer_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/peers/{peer_id}/chat"


def peer_representation(workspace_id: str, peer_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/peers/{peer_id}/representation"


def peer_card(workspace_id: str, peer_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/peers/{peer_id}/card"


def peer_context(workspace_id: str, peer_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/peers/{peer_id}/context"


def peer_search(workspace_id: str, peer_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/peers/{peer_id}/search"


def peer_sessions_list(workspace_id: str, peer_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/peers/{peer_id}/sessions"


# Session routes
def sessions(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions"


def sessions_list(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/list"


def session(workspace_id: str, session_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}"


def session_clone(workspace_id: str, session_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}/clone"


def session_context(workspace_id: str, session_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}/context"


def session_summaries(workspace_id: str, session_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}/summaries"


def session_search(workspace_id: str, session_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}/search"


def session_peers(workspace_id: str, session_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}/peers"


def session_peer_config(workspace_id: str, session_id: str, peer_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}/peers/{peer_id}/config"


# Message routes
def messages(workspace_id: str, session_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}/messages"


def messages_list(workspace_id: str, session_id: str) -> str:
    return (
        f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}/messages/list"
    )


def message(workspace_id: str, session_id: str, message_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}/messages/{message_id}"


def messages_upload(workspace_id: str, session_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/sessions/{session_id}/messages/upload"


# Conclusion routes
def conclusions(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/conclusions"


def conclusions_list(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/conclusions/list"


def conclusions_query(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/conclusions/query"


def conclusion(workspace_id: str, conclusion_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/conclusions/{conclusion_id}"


# Reasoning artifact routes
def hypotheses(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/hypotheses"


def hypothesis(workspace_id: str, hypothesis_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/hypotheses/{hypothesis_id}"


def hypothesis_predictions(workspace_id: str, hypothesis_id: str) -> str:
    return (
        f"/{API_VERSION}/workspaces/{workspace_id}/hypotheses"
        f"/{hypothesis_id}/predictions"
    )


def hypothesis_genealogy(workspace_id: str, hypothesis_id: str) -> str:
    return (
        f"/{API_VERSION}/workspaces/{workspace_id}/hypotheses/{hypothesis_id}/genealogy"
    )


def predictions(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/predictions"


def prediction(workspace_id: str, prediction_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/predictions/{prediction_id}"


def predictions_search(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/predictions/search"


def prediction_traces(workspace_id: str, prediction_id: str) -> str:
    return (
        f"/{API_VERSION}/workspaces/{workspace_id}/predictions/{prediction_id}/traces"
    )


def traces(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/traces"


def trace(workspace_id: str, trace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/traces/{trace_id}"


def inductions(workspace_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/inductions"


def induction(workspace_id: str, induction_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/inductions/{induction_id}"


def induction_sources(workspace_id: str, induction_id: str) -> str:
    return f"/{API_VERSION}/workspaces/{workspace_id}/inductions/{induction_id}/sources"
