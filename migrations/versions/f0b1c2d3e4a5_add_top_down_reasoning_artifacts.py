"""add top-down reasoning artifacts

Revision ID: f0b1c2d3e4a5
Revises: a8f2d4e6c9b1
Create Date: 2026-06-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from migrations.utils import column_exists, get_schema, index_exists
from src.config import settings

# revision identifiers, used by Alembic.
revision: str = "f0b1c2d3e4a5"
down_revision: str | None = "a8f2d4e6c9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

schema = get_schema()
vector_dim = settings.EMBEDDING.VECTOR_DIMENSIONS


def _ref(table_and_column: str) -> str:
    return f"{schema}.{table_and_column}" if schema else table_and_column


def upgrade() -> None:
    """Create top-down reasoning artifact storage."""
    inspector = sa.inspect(op.get_bind())

    if not column_exists("documents", "provenance_type", inspector):
        op.add_column(
            "documents",
            sa.Column("provenance_type", sa.TEXT(), nullable=True),
            schema=schema,
        )
    if not index_exists("documents", "ix_documents_provenance_type", inspector):
        op.create_index(
            "ix_documents_provenance_type",
            "documents",
            ["provenance_type"],
            schema=schema,
        )

    if not column_exists("documents", "agent_trace_id", inspector):
        op.add_column(
            "documents",
            sa.Column("agent_trace_id", sa.TEXT(), nullable=True),
            schema=schema,
        )
    if not index_exists("documents", "ix_documents_agent_trace_id", inspector):
        op.create_index(
            "ix_documents_agent_trace_id",
            "documents",
            ["agent_trace_id"],
            schema=schema,
        )

    op.create_table(
        "hypotheses",
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column(
            "status",
            sa.TEXT(),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            server_default=sa.text("0.5"),
            nullable=False,
        ),
        sa.Column(
            "source_premise_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
        sa.Column(
            "unaccounted_premises_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "search_coverage",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("tier", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "reasoning_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("superseded_by_id", sa.TEXT(), nullable=True),
        sa.Column(
            "supersedes_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
        sa.Column("observer", sa.TEXT(), nullable=False),
        sa.Column("observed", sa.TEXT(), nullable=False),
        sa.Column("workspace_name", sa.TEXT(), nullable=False),
        sa.Column("collection_id", sa.TEXT(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(id) = 21", name="hypothesis_id_length"),
        sa.CheckConstraint(
            "length(content) <= 65535",
            name="hypothesis_content_length",
        ),
        sa.CheckConstraint(
            "id ~ '^[A-Za-z0-9_-]+$'",
            name="hypothesis_id_format",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'falsified')",
            name="hypothesis_status_valid",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="hypothesis_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_name"],
            [_ref("workspaces.name")],
            name="fk_hypotheses_workspace_name",
        ),
        sa.ForeignKeyConstraint(
            ["observer", "workspace_name"],
            [_ref("peers.name"), _ref("peers.workspace_name")],
            name="fk_hypotheses_observer_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["observed", "workspace_name"],
            [_ref("peers.name"), _ref("peers.workspace_name")],
            name="fk_hypotheses_observed_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["observer", "observed", "workspace_name"],
            [
                _ref("collections.observer"),
                _ref("collections.observed"),
                _ref("collections.workspace_name"),
            ],
            name="fk_hypotheses_collection",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index("ix_hypotheses_status", "hypotheses", ["status"], schema=schema)
    op.create_index("ix_hypotheses_observer", "hypotheses", ["observer"], schema=schema)
    op.create_index("ix_hypotheses_observed", "hypotheses", ["observed"], schema=schema)
    op.create_index(
        "ix_hypotheses_workspace_name",
        "hypotheses",
        ["workspace_name"],
        schema=schema,
    )
    op.create_index(
        "ix_hypotheses_collection_id",
        "hypotheses",
        ["collection_id"],
        schema=schema,
    )
    op.create_index(
        "ix_hypotheses_created_at",
        "hypotheses",
        ["created_at"],
        schema=schema,
    )
    op.create_index(
        "ix_hypotheses_superseded_by_id",
        "hypotheses",
        ["superseded_by_id"],
        schema=schema,
    )
    op.create_index(
        "ix_hypotheses_source_premise_ids_gin",
        "hypotheses",
        ["source_premise_ids"],
        schema=schema,
        postgresql_using="gin",
    )

    op.create_table(
        "predictions",
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column(
            "status",
            sa.TEXT(),
            server_default="untested",
            nullable=False,
        ),
        sa.Column("hypothesis_id", sa.TEXT(), nullable=False),
        sa.Column(
            "source_hypothesis_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
        sa.Column(
            "is_blind",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("workspace_name", sa.TEXT(), nullable=False),
        sa.Column("collection_id", sa.TEXT(), nullable=True),
        sa.Column("embedding", Vector(vector_dim), nullable=False),  # pyright: ignore
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(id) = 21", name="prediction_id_length"),
        sa.CheckConstraint(
            "length(content) <= 65535",
            name="prediction_content_length",
        ),
        sa.CheckConstraint(
            "id ~ '^[A-Za-z0-9_-]+$'",
            name="prediction_id_format",
        ),
        sa.CheckConstraint(
            "status IN ('unfalsified', 'falsified', 'untested')",
            name="prediction_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["hypothesis_id"],
            [_ref("hypotheses.id")],
            name="fk_predictions_hypothesis_id",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_name"],
            [_ref("workspaces.name")],
            name="fk_predictions_workspace_name",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index("ix_predictions_status", "predictions", ["status"], schema=schema)
    op.create_index(
        "ix_predictions_hypothesis_id",
        "predictions",
        ["hypothesis_id"],
        schema=schema,
    )
    op.create_index(
        "ix_predictions_workspace_name",
        "predictions",
        ["workspace_name"],
        schema=schema,
    )
    op.create_index(
        "ix_predictions_collection_id",
        "predictions",
        ["collection_id"],
        schema=schema,
    )
    op.create_index(
        "ix_predictions_created_at",
        "predictions",
        ["created_at"],
        schema=schema,
    )
    op.create_index(
        "ix_predictions_source_hypothesis_ids_gin",
        "predictions",
        ["source_hypothesis_ids"],
        schema=schema,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_predictions_embedding_hnsw",
        "predictions",
        ["embedding"],
        schema=schema,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "falsification_traces",
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column("prediction_id", sa.TEXT(), nullable=False),
        sa.Column(
            "search_queries",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
        sa.Column(
            "contradicting_premise_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
        sa.Column(
            "reasoning_chain",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "final_status",
            sa.TEXT(),
            server_default="untested",
            nullable=False,
        ),
        sa.Column(
            "search_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "search_efficiency_score",
            sa.Float(),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
        sa.Column("workspace_name", sa.TEXT(), nullable=False),
        sa.Column("collection_id", sa.TEXT(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(id) = 21",
            name="falsification_trace_id_length",
        ),
        sa.CheckConstraint(
            "id ~ '^[A-Za-z0-9_-]+$'",
            name="falsification_trace_id_format",
        ),
        sa.CheckConstraint(
            "final_status IN ('unfalsified', 'falsified', 'untested')",
            name="falsification_trace_status_valid",
        ),
        sa.CheckConstraint(
            "search_efficiency_score >= 0.0 "
            "AND search_efficiency_score <= 1.0 "
            "OR search_efficiency_score IS NULL",
            name="falsification_trace_efficiency_range",
        ),
        sa.ForeignKeyConstraint(
            ["prediction_id"],
            [_ref("predictions.id")],
            name="fk_falsification_traces_prediction_id",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_name"],
            [_ref("workspaces.name")],
            name="fk_falsification_traces_workspace_name",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index(
        "ix_falsification_traces_prediction_id",
        "falsification_traces",
        ["prediction_id"],
        schema=schema,
    )
    op.create_index(
        "ix_falsification_traces_final_status",
        "falsification_traces",
        ["final_status"],
        schema=schema,
    )
    op.create_index(
        "ix_falsification_traces_workspace_name",
        "falsification_traces",
        ["workspace_name"],
        schema=schema,
    )
    op.create_index(
        "ix_falsification_traces_collection_id",
        "falsification_traces",
        ["collection_id"],
        schema=schema,
    )
    op.create_index(
        "ix_falsification_traces_created_at",
        "falsification_traces",
        ["created_at"],
        schema=schema,
    )
    op.create_index(
        "ix_falsification_traces_search_queries_gin",
        "falsification_traces",
        ["search_queries"],
        schema=schema,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_falsification_traces_contradicting_premise_ids_gin",
        "falsification_traces",
        ["contradicting_premise_ids"],
        schema=schema,
        postgresql_using="gin",
    )

    op.create_table(
        "inductions",
        sa.Column("id", sa.TEXT(), nullable=False),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column(
            "source_prediction_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_premise_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
        sa.Column("pattern_type", sa.TEXT(), nullable=False),
        sa.Column(
            "confidence",
            sa.TEXT(),
            server_default="medium",
            nullable=False,
        ),
        sa.Column(
            "stability_score",
            sa.Float(),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
        sa.Column("observer", sa.TEXT(), nullable=False),
        sa.Column("observed", sa.TEXT(), nullable=False),
        sa.Column("workspace_name", sa.TEXT(), nullable=False),
        sa.Column("collection_id", sa.TEXT(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(id) = 21", name="induction_id_length"),
        sa.CheckConstraint(
            "length(content) <= 65535",
            name="induction_content_length",
        ),
        sa.CheckConstraint(
            "id ~ '^[A-Za-z0-9_-]+$'",
            name="induction_id_format",
        ),
        sa.CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="induction_confidence_valid",
        ),
        sa.CheckConstraint(
            "pattern_type IN ("
            "'preference', 'behavior', 'personality', "
            "'tendency', 'temporal', 'conditional'"
            ")",
            name="induction_pattern_type_valid",
        ),
        sa.CheckConstraint(
            "stability_score >= 0.0 AND stability_score <= 1.0 "
            "OR stability_score IS NULL",
            name="induction_stability_range",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_name"],
            [_ref("workspaces.name")],
            name="fk_inductions_workspace_name",
        ),
        sa.ForeignKeyConstraint(
            ["observer", "workspace_name"],
            [_ref("peers.name"), _ref("peers.workspace_name")],
            name="fk_inductions_observer_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["observed", "workspace_name"],
            [_ref("peers.name"), _ref("peers.workspace_name")],
            name="fk_inductions_observed_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["observer", "observed", "workspace_name"],
            [
                _ref("collections.observer"),
                _ref("collections.observed"),
                _ref("collections.workspace_name"),
            ],
            name="fk_inductions_collection",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index("ix_inductions_observer", "inductions", ["observer"], schema=schema)
    op.create_index("ix_inductions_observed", "inductions", ["observed"], schema=schema)
    op.create_index(
        "ix_inductions_workspace_name",
        "inductions",
        ["workspace_name"],
        schema=schema,
    )
    op.create_index(
        "ix_inductions_collection_id",
        "inductions",
        ["collection_id"],
        schema=schema,
    )
    op.create_index(
        "ix_inductions_created_at",
        "inductions",
        ["created_at"],
        schema=schema,
    )
    op.create_index(
        "ix_inductions_pattern_type",
        "inductions",
        ["pattern_type"],
        schema=schema,
    )
    op.create_index(
        "ix_inductions_confidence",
        "inductions",
        ["confidence"],
        schema=schema,
    )
    op.create_index(
        "ix_inductions_source_prediction_ids_gin",
        "inductions",
        ["source_prediction_ids"],
        schema=schema,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_inductions_source_premise_ids_gin",
        "inductions",
        ["source_premise_ids"],
        schema=schema,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Drop top-down reasoning artifact storage."""
    op.drop_table("inductions", schema=schema)
    op.drop_table("falsification_traces", schema=schema)
    op.drop_table("predictions", schema=schema)
    op.drop_table("hypotheses", schema=schema)

    if index_exists("documents", "ix_documents_agent_trace_id"):
        op.drop_index(
            "ix_documents_agent_trace_id",
            table_name="documents",
            schema=schema,
        )
    if column_exists("documents", "agent_trace_id"):
        op.drop_column("documents", "agent_trace_id", schema=schema)

    if index_exists("documents", "ix_documents_provenance_type"):
        op.drop_index(
            "ix_documents_provenance_type",
            table_name="documents",
            schema=schema,
        )
    if column_exists("documents", "provenance_type"):
        op.drop_column("documents", "provenance_type", schema=schema)
