"""Bounded local-only message-vector reconciliation.

This CLI intentionally reconciles only pending ``message_embeddings`` rows. It
does not process representation, dialectic, dream, summary, document, or broad
deriver queue work. Receipts contain counts, IDs, and content hashes only.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import models
from src.config import resolve_embedding_model_config, settings
from src.db import engine
from src.dependencies import tracked_db
from src.embedding_client import embedding_client
from src.reconciler.sync_vectors import (
    ReconciliationMetrics,
    _reconcile_message_embeddings_batch,  # pyright: ignore[reportPrivateUsage]
)
from src.startup.embedding_validator import validate_embedding_schema
from src.vector_store import get_external_vector_store

DEFAULT_MANIFEST_DIR = Path("reports/vector-reconciliation")
SAFE_SYNTHETIC_QUERY = "operating decision routing status"


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_loopback_base_url(base_url: str | None) -> bool:
    if not base_url:
        return False
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
        "host.docker.internal",
        "ollama",
    }


def _assert_local_embedding_provider() -> dict[str, str | int | bool | None]:
    runtime = resolve_embedding_model_config(settings.EMBEDDING.MODEL_CONFIG)
    base_url = runtime.base_url
    local = runtime.transport == "ollama" or (
        runtime.transport == "openai" and _is_loopback_base_url(base_url)
    )
    if not local:
        raise SystemExit(
            "Refusing vector reconciliation: embedding provider is not local. "
            f"transport={runtime.transport!r} base_url={base_url!r}"
        )
    return {
        "transport": runtime.transport,
        "model": runtime.model,
        "base_url": base_url,
        "vector_dimensions": settings.EMBEDDING.VECTOR_DIMENSIONS,
        "local_provider": local,
    }


async def _vector_report() -> dict[str, object]:
    async with tracked_db("local_vector_reconcile_report", read_only=True) as db:
        scalar_rows = await db.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM messages) AS messages,
                  (SELECT count(*) FROM message_embeddings) AS message_embedding_records,
                  (SELECT count(*) FROM message_embeddings WHERE embedding IS NULL) AS null_vectors,
                  (SELECT count(*) FROM message_embeddings WHERE sync_state = 'pending') AS pending_records,
                  (SELECT count(*) FROM message_embeddings WHERE sync_state = 'synced') AS synced_records,
                  (SELECT count(*) FROM message_embeddings WHERE sync_state = 'failed') AS failed_records,
                  (SELECT count(DISTINCT public_id) FROM messages) AS distinct_messages,
                  (SELECT count(DISTINCT message_id) FROM message_embeddings) AS distinct_embedded_messages
                """
            )
        )
        row = scalar_rows.one()._mapping

        pending = (
            await db.execute(
                select(
                    models.MessageEmbedding.id,
                    models.MessageEmbedding.message_id,
                    models.MessageEmbedding.created_at,
                    models.MessageEmbedding.sync_attempts,
                    models.MessageEmbedding.content,
                )
                .where(models.MessageEmbedding.embedding.is_(None))
                .order_by(models.MessageEmbedding.created_at.asc())
                .limit(25)
            )
        ).all()

        missing_message_rows = (
            await db.execute(
                text(
                    """
                    SELECT m.public_id
                    FROM messages m
                    LEFT JOIN message_embeddings me ON me.message_id = m.public_id
                    WHERE me.id IS NULL
                    ORDER BY m.created_at ASC
                    LIMIT 50
                    """
                )
            )
        ).all()

        synthetic_probe = (
            await db.execute(
                text(
                    """
                    SELECT count(*)
                    FROM message_embeddings
                    WHERE embedding IS NOT NULL
                      AND sync_state = 'synced'
                    """
                )
            )
        ).scalar_one()

    oldest = pending[0].created_at.isoformat() if pending else None
    newest = pending[-1].created_at.isoformat() if pending else None
    return {
        "counts": dict(row),
        "pending_window": {"oldest": oldest, "newest_sampled": newest},
        "pending_sample": [
            {
                "embedding_id": item.id,
                "message_id": item.message_id,
                "message_id_hash": _hash(item.message_id),
                "content_hash": _hash(item.content),
                "sync_attempts": item.sync_attempts,
                "created_at": item.created_at.isoformat(),
            }
            for item in pending
        ],
        "missing_embedding_message_ids_sample": [
            {
                "message_id": item.public_id,
                "message_id_hash": _hash(item.public_id),
            }
            for item in missing_message_rows
        ],
        "synthetic_search_precondition": {
            "query": SAFE_SYNTHETIC_QUERY,
            "synced_vector_rows_available": synthetic_probe,
        },
    }


async def _run_batches(max_batches: int) -> ReconciliationMetrics:
    metrics = ReconciliationMetrics()
    external = get_external_vector_store()
    for _ in range(max_batches):
        did_work = await _reconcile_message_embeddings_batch(external, metrics)
        if not did_work:
            break
    return metrics


async def _release_leased_pending_null_vectors() -> int:
    async with tracked_db("local_vector_reconcile_release_leases") as db:
        rows = (
            await db.execute(
                select(models.MessageEmbedding.id)
                .where(models.MessageEmbedding.sync_state == "pending")
                .where(models.MessageEmbedding.embedding.is_(None))
            )
        ).scalars()
        ids = list(rows.all())
        if not ids:
            return 0
        for emb_id in ids:
            emb = await db.get(models.MessageEmbedding, emb_id)
            if emb is not None:
                emb.last_sync_at = None
        await db.commit()
        return len(ids)


async def _create_missing_embedding_rows() -> int:
    async with tracked_db("local_vector_reconcile_create_missing_rows") as db:
        messages = list(
            (
                await db.execute(
                    select(models.Message)
                    .outerjoin(
                        models.MessageEmbedding,
                        models.Message.public_id
                        == models.MessageEmbedding.message_id,
                    )
                    .where(models.MessageEmbedding.id.is_(None))
                    .where(models.Message.content.isnot(None))
                    .order_by(models.Message.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        id_resource_dict = {
            message.public_id: message.content
            for message in messages
            if message.content and message.content.strip()
        }
        if not id_resource_dict:
            return 0

        chunks_by_id = embedding_client.prepare_chunks(id_resource_dict)
        rows: list[models.MessageEmbedding] = []
        for message in messages:
            for chunk_text in chunks_by_id.get(message.public_id, []):
                rows.append(
                    models.MessageEmbedding(
                        content=chunk_text,
                        message_id=message.public_id,
                        workspace_name=message.workspace_name,
                        session_name=message.session_name,
                        peer_name=message.peer_name,
                        sync_state="pending",
                        embedding=None,
                    )
                )
        if not rows:
            return 0
        db.add_all(rows)
        await db.commit()
        return len(rows)


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--release-leased-pending", action="store_true")
    parser.add_argument("--create-missing-embedding-rows", action="store_true")
    parser.add_argument("--max-batches", type=int, default=20)
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    args = parser.parse_args()

    provider = _assert_local_embedding_provider()
    await validate_embedding_schema(engine)

    before = await _vector_report()
    metrics = ReconciliationMetrics()
    released_leases = 0
    created_missing_rows = 0
    started = time.monotonic()
    if args.execute:
        if args.create_missing_embedding_rows:
            created_missing_rows = await _create_missing_embedding_rows()
        if args.release_leased_pending:
            released_leases = await _release_leased_pending_null_vectors()
        metrics = await _run_batches(args.max_batches)
    after = await _vector_report()

    manifest = {
        "created_at": _utc_now(),
        "mode": "execute" if args.execute else "dry_run",
        "local_embedding_provider": provider,
        "scope": "message_embeddings_only",
        "deriver_reactivated": False,
        "remote_llm_allowed": False,
        "max_batches": args.max_batches,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "released_pending_leases": released_leases,
        "created_missing_embedding_rows": created_missing_rows,
        "before": before,
        "metrics": {
            "message_embeddings_synced": metrics.message_embeddings_synced,
            "message_embeddings_failed": metrics.message_embeddings_failed,
            "documents_synced": metrics.documents_synced,
            "documents_failed": metrics.documents_failed,
            "documents_cleaned": metrics.documents_cleaned,
        },
        "after": after,
    }
    args.manifest_dir.mkdir(parents=True, exist_ok=True)
    path = args.manifest_dir / f"message-vector-reconciliation-{_utc_now()}.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(path)
    print(json.dumps(manifest["after"]["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
