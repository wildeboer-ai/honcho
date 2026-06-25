import datetime
from logging import getLogger
from typing import Any, final

from dotenv import load_dotenv
from nanoid import generate as generate_nanoid
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TEXT
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column, relationship
from sqlalchemy.sql import func
from typing_extensions import override

from src.config import settings
from src.utils.types import DocumentLevel, TaskType, VectorSyncState

from .db import Base

load_dotenv(override=True)

_VECTOR_DIM: int = settings.EMBEDDING.VECTOR_DIMENSIONS

logger = getLogger(__name__)


# Association table for many-to-many relationship between sessions and peers
session_peers_table = Table(
    "session_peers",
    Base.metadata,
    Column(
        "workspace_name",
        TEXT,
        ForeignKey("workspaces.name"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "session_name",
        TEXT,
        primary_key=True,
        nullable=False,
    ),
    Column("peer_name", TEXT, primary_key=True, nullable=False),
    Column(
        "configuration",
        JSONB,
        default=dict,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "internal_metadata",
        JSONB,
        default=dict,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    Column(
        "joined_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "left_at",
        DateTime(timezone=True),
        nullable=True,
    ),
    # Composite foreign key constraint for sessions
    ForeignKeyConstraint(
        ["session_name", "workspace_name"],
        ["sessions.name", "sessions.workspace_name"],
    ),
    # Composite foreign key constraint for peers
    ForeignKeyConstraint(
        ["peer_name", "workspace_name"],
        ["peers.name", "peers.workspace_name"],
    ),
)


@final
class Workspace(Base):
    __tablename__: str = "workspaces"
    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)
    name: Mapped[str] = mapped_column(TEXT, unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    h_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    internal_metadata: Mapped[dict[str, Any]] = mapped_column(
        "internal_metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )

    sessions = relationship(
        "Session", back_populates="workspace", cascade="all, delete, delete-orphan"
    )
    peers = relationship(
        "Peer", back_populates="workspace", cascade="all, delete, delete-orphan"
    )
    webhook_endpoints = relationship("WebhookEndpoint", back_populates="workspace")

    __table_args__ = (
        CheckConstraint("length(id) = 21", name="id_length"),
        CheckConstraint("length(name) <= 512", name="name_length"),
        CheckConstraint("id ~ '^[A-Za-z0-9_-]+$'", name="id_format"),
    )


@final
class Peer(Base):
    __tablename__: str = "peers"
    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)
    name: Mapped[str] = mapped_column(TEXT, nullable=False)
    h_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    internal_metadata: Mapped[dict[str, Any]] = mapped_column(
        "internal_metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )

    workspace = relationship("Workspace", back_populates="peers")
    sessions = relationship(
        "Session", secondary=session_peers_table, back_populates="peers"
    )

    __table_args__ = (
        UniqueConstraint("name", "workspace_name"),
        CheckConstraint("length(id) = 21", name="id_length"),
        CheckConstraint("length(name) <= 512", name="name_length"),
        CheckConstraint("id ~ '^[A-Za-z0-9_-]+$'", name="id_format"),
    )

    def __repr__(self) -> str:
        return f"Peer(id={self.id}, name={self.name}, workspace_name={self.workspace_name}, created_at={self.created_at}, h_metadata={self.h_metadata}, configuration={self.configuration})"


@final
class Session(Base):
    __tablename__: str = "sessions"
    id: Mapped[str] = mapped_column(TEXT, primary_key=True, default=generate_nanoid)
    name: Mapped[str] = mapped_column(TEXT)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    h_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    internal_metadata: Mapped[dict[str, Any]] = mapped_column(
        "internal_metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )

    workspace = relationship("Workspace", back_populates="sessions")
    peers = relationship(
        "Peer", secondary=session_peers_table, back_populates="sessions"
    )
    messages = relationship("Message", back_populates="session")

    __table_args__ = (
        UniqueConstraint("name", "workspace_name"),
        CheckConstraint("length(name) <= 512", name="name_length"),
        CheckConstraint("length(id) = 21", name="id_length"),
        CheckConstraint("id ~ '^[A-Za-z0-9_-]+$'", name="id_format"),
    )

    def __repr__(self) -> str:
        return f"Session(id={self.id}, name={self.name}, workspace_name={self.workspace_name}, is_active={self.is_active}, created_at={self.created_at}, h_metadata={self.h_metadata})"


@final
class Message(Base):
    __tablename__: str = "messages"
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(
        TEXT,
        unique=True,
        default=generate_nanoid,
    )
    # NOTE: Messages in Honcho 2.0 could historically be stored outside of a session.
    # We have since assigned all of these messages to a default session.
    session_name: Mapped[str] = mapped_column(TEXT, nullable=False)
    content: Mapped[str] = mapped_column(TEXT)
    h_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    internal_metadata: Mapped[dict[str, Any]] = mapped_column(
        "internal_metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    seq_in_session: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Note: Foreign key relationships established via composite ForeignKeyConstraint below
    peer_name: Mapped[str] = mapped_column(TEXT, index=True)
    workspace_name: Mapped[str] = mapped_column(TEXT, index=True)

    session = relationship("Session", back_populates="messages")

    __table_args__ = (
        CheckConstraint("length(public_id) = 21", name="public_id_length"),
        CheckConstraint("public_id ~ '^[A-Za-z0-9_-]+$'", name="public_id_format"),
        CheckConstraint("length(content) <= 65535", name="content_length"),
        # Composite foreign key constraint for sessions
        ForeignKeyConstraint(
            ["session_name", "workspace_name"],
            ["sessions.name", "sessions.workspace_name"],
        ),
        # Composite foreign key constraint for peers
        ForeignKeyConstraint(
            ["peer_name", "workspace_name"],
            ["peers.name", "peers.workspace_name"],
        ),
        Index(
            "ix_messages_session_lookup",
            "session_name",
            "id",
            postgresql_include=["id", "created_at"],
        ),
        UniqueConstraint(
            "workspace_name",
            "session_name",
            "seq_in_session",
        ),
        # Full text search index on content column
        Index(
            "ix_messages_content_gin",
            text("to_tsvector('english', content)"),
            postgresql_using="gin",
        ),
    )

    @override
    def __repr__(self) -> str:
        return f"Message(id={self.id}, session_name={self.session_name}, peer_name={self.peer_name}, content={self.content})"


@final
class MessageEmbedding(Base):
    __tablename__: str = "message_embeddings"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, autoincrement=True
    )
    content: Mapped[str] = mapped_column(TEXT)
    embedding: MappedColumn[Any] = mapped_column(Vector(_VECTOR_DIM), nullable=True)
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.public_id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )
    session_name: Mapped[str] = mapped_column(TEXT, nullable=False, index=True)
    peer_name: Mapped[str] = mapped_column(TEXT, nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Vector sync state tracking
    sync_state: Mapped[VectorSyncState] = mapped_column(
        TEXT, nullable=False, server_default="pending", index=True
    )
    last_sync_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        # Compound foreign key constraints
        ForeignKeyConstraint(
            ["session_name", "workspace_name"],
            ["sessions.name", "sessions.workspace_name"],
        ),
        ForeignKeyConstraint(
            ["peer_name", "workspace_name"],
            ["peers.name", "peers.workspace_name"],
        ),
        # HNSW index on embedding column for efficient similarity search
        Index(
            "ix_message_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Composite index for efficient reconciliation queries
        Index(
            "ix_message_embeddings_sync_state_last_sync_at",
            "sync_state",
            "last_sync_at",
        ),
    )


@final
class Collection(Base):
    __tablename__: str = "collections"

    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)
    observer: Mapped[str] = mapped_column(TEXT, index=True)
    observed: Mapped[str] = mapped_column(TEXT, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    h_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    internal_metadata: Mapped[dict[str, Any]] = mapped_column(
        "internal_metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    documents = relationship(
        "Document", back_populates="collection", cascade="all, delete, delete-orphan"
    )
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "observer",
            "observed",
            "workspace_name",
        ),
        CheckConstraint("length(id) = 21", name="id_length"),
        CheckConstraint("id ~ '^[A-Za-z0-9_-]+$'", name="id_format"),
        # Composite foreign key constraint for observer peer
        ForeignKeyConstraint(
            ["observer", "workspace_name"],
            ["peers.name", "peers.workspace_name"],
        ),
        # Composite foreign key constraint for observed peer
        ForeignKeyConstraint(
            ["observed", "workspace_name"],
            ["peers.name", "peers.workspace_name"],
        ),
    )


@final
class Document(Base):
    __tablename__: str = "documents"
    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)
    internal_metadata: Mapped[dict[str, Any]] = mapped_column(
        "internal_metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    content: Mapped[str] = mapped_column(TEXT)
    level: Mapped[DocumentLevel] = mapped_column(
        TEXT, nullable=False, server_default="explicit"
    )
    times_derived: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    embedding: MappedColumn[Any] = mapped_column(Vector(_VECTOR_DIM), nullable=True)
    source_ids: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("NULL")
    )
    provenance_type: Mapped[str | None] = mapped_column(TEXT, nullable=True, index=True)
    agent_trace_id: Mapped[str | None] = mapped_column(TEXT, nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    observer: Mapped[str] = mapped_column(TEXT, index=True)
    observed: Mapped[str] = mapped_column(TEXT, index=True)
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )
    session_name: Mapped[str | None] = mapped_column(TEXT, nullable=True, index=True)
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, default=None
    )

    # Vector sync state tracking
    sync_state: Mapped[VectorSyncState] = mapped_column(
        TEXT, nullable=False, server_default="pending", index=True
    )
    last_sync_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    collection = relationship("Collection", back_populates="documents")

    __table_args__ = (
        CheckConstraint("length(id) = 21", name="id_length"),
        CheckConstraint("length(content) <= 65535", name="content_length"),
        CheckConstraint("id ~ '^[A-Za-z0-9_-]+$'", name="id_format"),
        # Composite foreign key constraint for collections
        ForeignKeyConstraint(
            ["observer", "observed", "workspace_name"],
            [
                "collections.observer",
                "collections.observed",
                "collections.workspace_name",
            ],
        ),
        # Composite foreign key constraint for observer peer
        ForeignKeyConstraint(
            ["observer", "workspace_name"],
            ["peers.name", "peers.workspace_name"],
        ),
        # Composite foreign key constraint for observed peer
        ForeignKeyConstraint(
            ["observed", "workspace_name"],
            ["peers.name", "peers.workspace_name"],
        ),
        # Composite foreign key constraint for sessions
        ForeignKeyConstraint(
            ["session_name", "workspace_name"],
            ["sessions.name", "sessions.workspace_name"],
        ),
        # HNSW index on embedding column
        Index(
            "ix_documents_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",  # HNSW index type
            postgresql_with={"m": 16, "ef_construction": 64},  # HNSW parameters
            postgresql_ops={
                "embedding": "vector_cosine_ops"
            },  # Cosine distance operator
        ),
        # GIN index for efficient tree traversal (finding children by source IDs)
        Index(
            "ix_documents_source_ids_gin",
            "source_ids",
            postgresql_using="gin",
        ),
        # Composite index for efficient reconciliation queries
        Index(
            "ix_documents_sync_state_last_sync_at",
            "sync_state",
            "last_sync_at",
        ),
    )


@final
class Hypothesis(Base):
    """Explanatory hypothesis generated by top-down reasoning."""

    __tablename__: str = "hypotheses"

    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)
    content: Mapped[str] = mapped_column(TEXT)
    status: Mapped[str] = mapped_column(
        TEXT, nullable=False, server_default="active", index=True
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.5")
    )
    source_premise_ids: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("NULL")
    )
    unaccounted_premises_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    search_coverage: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    tier: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    reasoning_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    superseded_by_id: Mapped[str | None] = mapped_column(
        TEXT, nullable=True, index=True
    )
    supersedes_ids: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("NULL")
    )
    observer: Mapped[str] = mapped_column(TEXT, index=True)
    observed: Mapped[str] = mapped_column(TEXT, index=True)
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )
    collection_id: Mapped[str | None] = mapped_column(TEXT, nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("length(id) = 21", name="hypothesis_id_length"),
        CheckConstraint("length(content) <= 65535", name="hypothesis_content_length"),
        CheckConstraint("id ~ '^[A-Za-z0-9_-]+$'", name="hypothesis_id_format"),
        CheckConstraint(
            "status IN ('active', 'superseded', 'falsified')",
            name="hypothesis_status_valid",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="hypothesis_confidence_range",
        ),
        ForeignKeyConstraint(
            ["observer", "workspace_name"],
            ["peers.name", "peers.workspace_name"],
        ),
        ForeignKeyConstraint(
            ["observed", "workspace_name"],
            ["peers.name", "peers.workspace_name"],
        ),
        ForeignKeyConstraint(
            ["observer", "observed", "workspace_name"],
            [
                "collections.observer",
                "collections.observed",
                "collections.workspace_name",
            ],
        ),
        Index(
            "ix_hypotheses_source_premise_ids_gin",
            "source_premise_ids",
            postgresql_using="gin",
        ),
    )


@final
class Prediction(Base):
    """Testable prediction generated from a hypothesis."""

    __tablename__: str = "predictions"

    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)
    content: Mapped[str] = mapped_column(TEXT)
    status: Mapped[str] = mapped_column(
        TEXT, nullable=False, server_default="untested", index=True
    )
    hypothesis_id: Mapped[str] = mapped_column(TEXT, nullable=False, index=True)
    source_hypothesis_ids: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("NULL")
    )
    is_blind: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )
    collection_id: Mapped[str | None] = mapped_column(TEXT, nullable=True, index=True)
    embedding: MappedColumn[Any] = mapped_column(Vector(_VECTOR_DIM), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        CheckConstraint("length(id) = 21", name="prediction_id_length"),
        CheckConstraint("length(content) <= 65535", name="prediction_content_length"),
        CheckConstraint("id ~ '^[A-Za-z0-9_-]+$'", name="prediction_id_format"),
        CheckConstraint(
            "status IN ('unfalsified', 'falsified', 'untested')",
            name="prediction_status_valid",
        ),
        ForeignKeyConstraint(["hypothesis_id"], ["hypotheses.id"]),
        Index(
            "ix_predictions_source_hypothesis_ids_gin",
            "source_hypothesis_ids",
            postgresql_using="gin",
        ),
        Index(
            "ix_predictions_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


@final
class FalsificationTrace(Base):
    """Append-only trace of falsification work for a prediction."""

    __tablename__: str = "falsification_traces"

    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)
    prediction_id: Mapped[str] = mapped_column(TEXT, nullable=False, index=True)
    search_queries: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("NULL")
    )
    contradicting_premise_ids: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("NULL")
    )
    reasoning_chain: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    final_status: Mapped[str] = mapped_column(
        TEXT, nullable=False, server_default="untested", index=True
    )
    search_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    search_efficiency_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default=text("NULL")
    )
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )
    collection_id: Mapped[str | None] = mapped_column(TEXT, nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        CheckConstraint("length(id) = 21", name="falsification_trace_id_length"),
        CheckConstraint(
            "id ~ '^[A-Za-z0-9_-]+$'", name="falsification_trace_id_format"
        ),
        CheckConstraint(
            "final_status IN ('unfalsified', 'falsified', 'untested')",
            name="falsification_trace_status_valid",
        ),
        CheckConstraint(
            "search_efficiency_score >= 0.0 AND search_efficiency_score <= 1.0 OR search_efficiency_score IS NULL",
            name="falsification_trace_efficiency_range",
        ),
        ForeignKeyConstraint(["prediction_id"], ["predictions.id"]),
        Index(
            "ix_falsification_traces_search_queries_gin",
            "search_queries",
            postgresql_using="gin",
        ),
        Index(
            "ix_falsification_traces_contradicting_premise_ids_gin",
            "contradicting_premise_ids",
            postgresql_using="gin",
        ),
    )


@final
class Induction(Base):
    """Pattern extracted from unfalsified predictions."""

    __tablename__: str = "inductions"

    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)
    content: Mapped[str] = mapped_column(TEXT)
    source_prediction_ids: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("NULL")
    )
    source_premise_ids: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, server_default=text("NULL")
    )
    pattern_type: Mapped[str] = mapped_column(TEXT, nullable=False, index=True)
    confidence: Mapped[str] = mapped_column(
        TEXT, nullable=False, server_default="medium", index=True
    )
    stability_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default=text("NULL")
    )
    observer: Mapped[str] = mapped_column(TEXT, index=True)
    observed: Mapped[str] = mapped_column(TEXT, index=True)
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )
    collection_id: Mapped[str | None] = mapped_column(TEXT, nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        CheckConstraint("length(id) = 21", name="induction_id_length"),
        CheckConstraint("length(content) <= 65535", name="induction_content_length"),
        CheckConstraint("id ~ '^[A-Za-z0-9_-]+$'", name="induction_id_format"),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="induction_confidence_valid",
        ),
        CheckConstraint(
            "pattern_type IN ('preference', 'behavior', 'personality', 'tendency', 'temporal', 'conditional')",
            name="induction_pattern_type_valid",
        ),
        CheckConstraint(
            "stability_score >= 0.0 AND stability_score <= 1.0 OR stability_score IS NULL",
            name="induction_stability_range",
        ),
        ForeignKeyConstraint(
            ["observer", "workspace_name"],
            ["peers.name", "peers.workspace_name"],
        ),
        ForeignKeyConstraint(
            ["observed", "workspace_name"],
            ["peers.name", "peers.workspace_name"],
        ),
        ForeignKeyConstraint(
            ["observer", "observed", "workspace_name"],
            [
                "collections.observer",
                "collections.observed",
                "collections.workspace_name",
            ],
        ),
        Index(
            "ix_inductions_source_prediction_ids_gin",
            "source_prediction_ids",
            postgresql_using="gin",
        ),
        Index(
            "ix_inductions_source_premise_ids_gin",
            "source_premise_ids",
            postgresql_using="gin",
        ),
    )


@final
class QueueItem(Base):
    __tablename__: str = "queue"
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True, autoincrement=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("sessions.id"), nullable=True, index=True
    )
    work_unit_key: Mapped[str] = mapped_column(TEXT, nullable=False)

    task_type: Mapped[TaskType] = mapped_column(TEXT, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), index=True
    )
    error: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    workspace_name: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.name"), nullable=True, index=True
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_queue_message_id_not_null",
            "message_id",
            postgresql_where=text("message_id IS NOT NULL"),
        ),
        Index(
            "ix_queue_work_unit_key_processed_id",
            "work_unit_key",
            "processed",
            "id",
        ),
        # Partial unique index for reconciler task deduplication
        Index(
            "uq_queue_reconciler_pending_work_unit_key",
            "work_unit_key",
            unique=True,
            postgresql_where=text("task_type = 'reconciler' AND processed = false"),
        ),
        # Partial unique index for dream task deduplication
        Index(
            "uq_queue_dream_pending_work_unit_key",
            "work_unit_key",
            unique=True,
            postgresql_where=text("task_type = 'dream' AND processed = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"QueueItem(id={self.id}, session_id={self.session_id}, work_unit_key={self.work_unit_key}, task_type={self.task_type}, payload={self.payload}, processed={self.processed}, workspace_name={self.workspace_name}, message_id={self.message_id})"


@final
class ActiveQueueSession(Base):
    __tablename__: str = "active_queue_sessions"

    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)

    work_unit_key: Mapped[str] = mapped_column(TEXT, unique=True)

    last_updated: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


@final
class WebhookEndpoint(Base):
    __tablename__: str = "webhook_endpoints"
    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(TEXT, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    workspace = relationship("Workspace", back_populates="webhook_endpoints")

    __table_args__ = (CheckConstraint("length(url) <= 2048", name="url_length"),)

    def __repr__(self) -> str:
        return f"WebhookEndpoint(id={self.id}, workspace_name={self.workspace_name}, url={self.url})"


@final
class SessionPeer(Base):
    __table__: Table = session_peers_table

    # Type annotations for the columns
    workspace_name: Mapped[str]
    session_name: Mapped[str]
    peer_name: Mapped[str]
    configuration: Mapped[dict[str, Any]]
    internal_metadata: Mapped[dict[str, Any]]
    joined_at: Mapped[datetime.datetime]
    left_at: Mapped[datetime.datetime | None]


@final
class DialecticTrace(Base):
    """Internal logging of dialectic interactions for meta-cognitive analysis."""

    __tablename__: str = "dialectic_traces"

    id: Mapped[str] = mapped_column(TEXT, default=generate_nanoid, primary_key=True)
    workspace_name: Mapped[str] = mapped_column(
        ForeignKey("workspaces.name"), nullable=False, index=True
    )
    session_name: Mapped[str | None] = mapped_column(TEXT, nullable=True, index=True)
    observer: Mapped[str] = mapped_column(TEXT, nullable=False, index=True)
    observed: Mapped[str] = mapped_column(TEXT, nullable=False, index=True)
    query: Mapped[str] = mapped_column(TEXT, nullable=False)
    retrieved_doc_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    response: Mapped[str] = mapped_column(TEXT, nullable=False)
    reasoning_level: Mapped[str] = mapped_column(TEXT, nullable=False)
    total_duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
