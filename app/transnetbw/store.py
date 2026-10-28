"""
Persistence for iris_staging: signals, their versions, the fetch ledger and
the run audit.

Two connections per run, on purpose:

  - RunLog runs in autocommit on its own connection: the ingest_run row,
    every ingest_issue and the advisory lock. What it writes survives a
    run whose data is rolled back, so a failed run is always visible.
  - SignalStore works inside the run's single data transaction, one
    savepoint per record, so a record the database rejects is rolled back
    alone while the run carries on.

Idempotency: a record is identified by (source_system, source_record_id)
and changes only when its content hash does. The same content again
refreshes only "last seen" audit fields; changed content updates the row
and adds a version; content flipping back to an earlier version reuses
that version.
"""

from __future__ import annotations

import json
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from app.transnetbw.normalize import SignalRecord


SCHEMA = "iris_staging"


def _json(value) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


@dataclass(frozen=True)
class UpsertOutcome:

    action: str

    signal_id: int

    page_changed: bool = False

    unretired: bool = False


@dataclass(frozen=True)
class LedgerEntry:

    url: str

    doc_kind: str

    sitemap_lastmod: datetime | None

    last_outcome: str | None

    raw_sha256: str | None


# =========================================================
# RUN LOG (autocommit)
# =========================================================


class RunLog:

    LOCK_SQL = "hashtext('iris_staging.signal_ingest'), hashtext(:source)"

    def __init__(self, engine: Engine, source_system: str):

        self.source_system = source_system

        self._conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")

        self._locked = False

    def _execute(self, sql: str, **params):
        return self._conn.execute(sa.text(sql), params)

    # =====================================================
    # CONCURRENCY
    # =====================================================

    def acquire_lock(self) -> bool:
        """
        Session-level advisory lock, held on this connection for the run.
        Released automatically if the process dies.
        """

        self._locked = bool(
            self._execute(
                f"select pg_try_advisory_lock({self.LOCK_SQL})",
                source=self.source_system,
            ).scalar_one()
        )

        return self._locked

    def release_lock(self) -> None:

        if self._locked:
            self._execute(f"select pg_advisory_unlock({self.LOCK_SQL})", source=self.source_system)
            self._locked = False

    def other_mode_present(self, mode: str) -> bool:
        """
        Fixture (offline) and live runs never share a database.
        """

        return bool(
            self._execute(
                f"""
                select exists (
                    select 1 from {SCHEMA}.ingest_run
                    where source_system = :source and mode <> :mode and status <> 'refused'
                )
                """,
                source=self.source_system,
                mode=mode,
            ).scalar_one()
        )

    # =====================================================
    # RUN RECORDS
    # =====================================================

    def start(self, mode: str, config: dict, code_version: str | None, status: str = "running") -> uuid.UUID:

        return self._execute(
            f"""
            insert into {SCHEMA}.ingest_run (source_system, mode, status, config, code_version)
            values (:source, :mode, :status, cast(:config as jsonb), :code_version)
            returning run_id
            """,
            source=self.source_system,
            mode=mode,
            status=status,
            config=_json(config),
            code_version=code_version,
        ).scalar_one()

    def issue(
        self,
        run_id: uuid.UUID,
        severity: str,
        code: str,
        message: str,
        *,
        source_record_id: str | None = None,
        source_url: str | None = None,
        context: dict | None = None,
    ) -> None:

        self._execute(
            f"""
            insert into {SCHEMA}.ingest_issue
                (run_id, severity, code, source_record_id, source_url, message, context)
            values
                (:run_id, :severity, :code, :record, :url, :message, cast(:context as jsonb))
            """,
            run_id=run_id,
            severity=severity,
            code=code,
            record=source_record_id,
            url=source_url,
            message=message,
            context=_json(context),
        )

    def finish(self, run_id: uuid.UUID, status: str, exit_code: int, stats: dict, gates: dict) -> None:

        self._execute(
            f"""
            update {SCHEMA}.ingest_run
            set status = :status, exit_code = :exit_code, finished_at = now(),
                stats = cast(:stats as jsonb), gates = cast(:gates as jsonb)
            where run_id = :run_id
            """,
            run_id=run_id,
            status=status,
            exit_code=exit_code,
            stats=_json(stats),
            gates=_json(gates),
        )

    def close(self) -> None:

        try:
            self.release_lock()

        finally:
            self._conn.close()


# =========================================================
# SIGNAL STORE (inside the run's transaction)
# =========================================================


SIGNAL_COLUMNS = """
    record_kind = :record_kind,
    signal_type = :signal_type,
    project_stage = :project_stage,
    review_status = :review_status,
    title = :title,
    summary = :summary,
    source_url = :source_url,
    language = :language,
    published_at = :published_at,
    published_at_verified = :published_at_verified,
    country_code = :country_code,
    region_code = :region_code,
    location_text = :location_text,
    location_status = :location_status,
    location_precision = :location_precision,
    location_method = :location_method,
    geom = ST_SetSRID(ST_MakePoint(cast(:x as double precision), cast(:y as double precision)), 25832),
    attributes = cast(:attributes as jsonb),
    quality_flags = cast(:quality_flags as text[]),
    content_hash = :content_hash
"""

AUDIT_COLUMNS = """
    raw_sha256 = :raw_sha256,
    source_last_modified = :source_last_modified,
    last_seen_run_id = :run_id,
    last_seen_at = :now,
    missing_run_count = 0,
    retired_at = null
"""


class SignalStore:

    def __init__(self, connection: Connection, source_system: str):

        self.conn = connection

        self.source_system = source_system

    def _execute(self, sql: str, **params):
        return self.conn.execute(sa.text(sql), params)

    def savepoint(self) -> AbstractContextManager:
        """
        `with store.savepoint():` — commits on success, rolls back only this
        block on an exception (which propagates).
        """

        return self.conn.begin_nested()

    # =====================================================
    # SIGNALS
    # =====================================================

    def _params(self, record: SignalRecord, run_id: uuid.UUID, now: datetime) -> dict:

        return {
            "source_system": record.source_system,
            "source_record_id": record.source_record_id,
            "record_kind": record.record_kind,
            "signal_type": record.signal_type,
            "project_stage": record.project_stage,
            "review_status": record.review_status,
            "title": record.title,
            "summary": record.summary,
            "source_url": record.source_url,
            "language": record.language,
            "published_at": record.published_at,
            "published_at_verified": record.published_at_verified,
            "country_code": record.country_code,
            "region_code": record.region_code,
            "location_text": record.location_text,
            "location_status": record.location_status,
            "location_precision": record.location_precision,
            "location_method": record.location_method,
            "x": record.x,
            "y": record.y,
            "attributes": _json(record.attributes),
            "quality_flags": sorted(set(record.quality_flags)),
            "content_hash": record.content_hash(),
            "raw_sha256": record.raw_sha256,
            "source_last_modified": record.source_last_modified,
            "run_id": run_id,
            "now": now,
        }

    def _add_version(self, signal_id: int, record: SignalRecord, run_id: uuid.UUID) -> bool:

        created = self._execute(
            f"""
            insert into {SCHEMA}.signal_ingest_version (signal_id, content_hash, payload, run_id)
            values (:signal_id, :content_hash, cast(:payload as jsonb), :run_id)
            on conflict (signal_id, content_hash) do nothing
            returning id
            """,
            signal_id=signal_id,
            content_hash=record.content_hash(),
            payload=_json(record.payload()),
            run_id=run_id,
        ).first()

        return created is not None

    def upsert(self, record: SignalRecord, run_id: uuid.UUID, now: datetime) -> UpsertOutcome:

        params = self._params(record, run_id, now)

        current = self._execute(
            f"""
            select id, content_hash, raw_sha256, retired_at
            from {SCHEMA}.signal_ingest
            where source_system = :source_system and source_record_id = :source_record_id
            for update
            """,
            **params,
        ).first()

        if current is None:

            inserted = self._execute(
                f"""
                insert into {SCHEMA}.signal_ingest (
                    source_system, source_record_id, record_kind, signal_type, project_stage,
                    review_status, title, summary, source_url, language, published_at,
                    published_at_verified, source_last_modified, country_code, region_code,
                    location_text, location_status, location_precision, location_method, geom,
                    attributes, quality_flags, content_hash, raw_sha256,
                    first_seen_run_id, last_seen_run_id, first_seen_at, last_seen_at
                ) values (
                    :source_system, :source_record_id, :record_kind, :signal_type, :project_stage,
                    :review_status, :title, :summary, :source_url, :language, :published_at,
                    :published_at_verified, :source_last_modified, :country_code, :region_code,
                    :location_text, :location_status, :location_precision, :location_method,
                    ST_SetSRID(ST_MakePoint(cast(:x as double precision), cast(:y as double precision)), 25832),
                    cast(:attributes as jsonb), cast(:quality_flags as text[]), :content_hash, :raw_sha256,
                    :run_id, :run_id, :now, :now
                )
                on conflict (source_system, source_record_id) do nothing
                returning id
                """,
                **params,
            ).first()

            if inserted is None:
                raise RuntimeError(f"concurrent insert of {record.source_record_id} despite the run lock")

            self._add_version(inserted.id, record, run_id)

            return UpsertOutcome("inserted", inserted.id)

        unretired = current.retired_at is not None

        if current.content_hash == params["content_hash"]:

            self._execute(
                f"update {SCHEMA}.signal_ingest set {AUDIT_COLUMNS} where id = :id",
                id=current.id,
                **params,
            )

            return UpsertOutcome(
                "unchanged",
                current.id,
                page_changed=current.raw_sha256 != record.raw_sha256,
                unretired=unretired,
            )

        self._execute(
            f"""
            update {SCHEMA}.signal_ingest
            set {SIGNAL_COLUMNS}, {AUDIT_COLUMNS}, updated_at = now()
            where id = :id
            """,
            id=current.id,
            **params,
        )

        created = self._add_version(current.id, record, run_id)

        return UpsertOutcome("updated" if created else "reverted", current.id, unretired=unretired)

    # =====================================================
    # LIFECYCLE
    # =====================================================

    def mark_seen(self, record_kind: str, keys: set[str], run_id: uuid.UUID, now: datetime) -> int:
        """
        Records the source still lists, fetched this run or not (an unchanged
        sitemap lastmod skips the fetch, not the record).
        """

        return self._execute(
            f"""
            update {SCHEMA}.signal_ingest
            set last_seen_run_id = :run_id, last_seen_at = :now,
                missing_run_count = 0, retired_at = null
            where source_system = :source and record_kind = :kind
              and source_record_id = any(cast(:keys as text[]))
            """,
            source=self.source_system,
            kind=record_kind,
            keys=sorted(keys),
            run_id=run_id,
            now=now,
        ).rowcount

    def mark_missing(self, record_kind: str, seen_keys: set[str], retire_after: int) -> tuple[int, int]:
        """
        Count a miss for every live record the source no longer lists, and
        retire those missed `retire_after` runs in a row. Returns
        (missed, newly retired).
        """

        rows = self._execute(
            f"""
            update {SCHEMA}.signal_ingest
            set missing_run_count = missing_run_count + 1,
                retired_at = case when missing_run_count + 1 >= :retire_after then now() else null end
            where source_system = :source and record_kind = :kind and retired_at is null
              and not (source_record_id = any(cast(:keys as text[])))
            returning retired_at is not null as retired
            """,
            source=self.source_system,
            kind=record_kind,
            keys=sorted(seen_keys),
            retire_after=retire_after,
        ).all()

        return len(rows), sum(1 for row in rows if row.retired)

    def refresh_derived(self) -> int:
        """
        Cross-record facts on project rows, from their linked press
        releases. Stored in `derived`, outside the content hash and the
        version history, so a new press release never "changes" a project.
        """

        return self._execute(
            f"""
            with press as (
                select attributes ->> 'related_project' as project_key,
                       published_at, project_stage, source_url
                from {SCHEMA}.signal_ingest
                where source_system = :source and record_kind = 'press_release'
                  and retired_at is null and attributes ? 'related_project'
            ),
            summary as (
                select project_key,
                       min(published_at) as first_reported_at,
                       count(*) as press_count,
                       (array_agg(
                            jsonb_build_object('date', published_at, 'stage', project_stage, 'url', source_url)
                            order by published_at desc nulls last, source_url
                       ))[1] as latest_event
                from press
                group by project_key
            ),
            target as (
                select project.id,
                       jsonb_strip_nulls(jsonb_build_object(
                           'first_reported_at', summary.first_reported_at,
                           'latest_event', summary.latest_event,
                           'related_press_count', summary.press_count
                       )) as derived
                from {SCHEMA}.signal_ingest project
                left join summary on summary.project_key = project.source_record_id
                where project.source_system = :source and project.record_kind = 'project'
            )
            update {SCHEMA}.signal_ingest signal
            set derived = target.derived
            from target
            where signal.id = target.id and signal.derived is distinct from target.derived
            """,
            source=self.source_system,
        ).rowcount

    def project_locations(self) -> dict[str, dict]:
        """
        Stored location of every live project, keyed by source_record_id —
        including projects not re-fetched this run, so a press release can
        inherit the point of a project whose page did not change.
        """

        rows = self._execute(
            f"""
            select source_record_id, location_status, location_text, location_precision,
                   ST_X(geom) as x, ST_Y(geom) as y,
                   attributes -> 'endpoints' as endpoints,
                   attributes -> 'regions' as regions,
                   attributes ->> 'location_source' as source,
                   quality_flags
            from {SCHEMA}.signal_ingest
            where source_system = :source and record_kind = 'project' and retired_at is null
            """,
            source=self.source_system,
        ).mappings().all()

        return {row["source_record_id"]: dict(row) for row in rows}

    # =====================================================
    # GATE INPUTS
    # =====================================================

    def resolved_count(self) -> int:

        return self._execute(
            f"""
            select count(*) from {SCHEMA}.signal_ingest
            where source_system = :source and location_status = 'resolved' and retired_at is null
            """,
            source=self.source_system,
        ).scalar_one()

    # =====================================================
    # FETCH LEDGER
    # =====================================================

    def ledger(self) -> dict[str, LedgerEntry]:

        rows = self._execute(
            f"""
            select url, doc_kind, sitemap_lastmod, last_outcome, raw_sha256
            from {SCHEMA}.source_document
            where source_system = :source
            """,
            source=self.source_system,
        ).all()

        return {
            row.url: LedgerEntry(row.url, row.doc_kind, row.sitemap_lastmod, row.last_outcome, row.raw_sha256)
            for row in rows
        }

    def record_document(
        self,
        *,
        url: str,
        doc_kind: str,
        sitemap_lastmod: datetime | None,
        http_status: int | None,
        raw_sha256: str | None,
        outcome: str,
        run_id: uuid.UUID,
        fetched_at: datetime | None,
    ) -> None:

        self._execute(
            f"""
            insert into {SCHEMA}.source_document (
                url, source_system, doc_kind, sitemap_lastmod, last_fetched_at,
                last_http_status, raw_sha256, last_outcome, last_run_id, updated_at
            ) values (
                :url, :source, :doc_kind, :lastmod, :fetched_at,
                :status, :sha, :outcome, :run_id, now()
            )
            on conflict (url) do update set
                doc_kind = excluded.doc_kind,
                sitemap_lastmod = excluded.sitemap_lastmod,
                last_fetched_at = coalesce(excluded.last_fetched_at, {SCHEMA}.source_document.last_fetched_at),
                last_http_status = coalesce(excluded.last_http_status, {SCHEMA}.source_document.last_http_status),
                raw_sha256 = coalesce(excluded.raw_sha256, {SCHEMA}.source_document.raw_sha256),
                last_outcome = excluded.last_outcome,
                last_run_id = excluded.last_run_id,
                updated_at = now()
            """,
            url=url,
            source=self.source_system,
            doc_kind=doc_kind,
            lastmod=sitemap_lastmod,
            fetched_at=fetched_at,
            status=http_status,
            sha=raw_sha256,
            outcome=outcome,
            run_id=run_id,
        )
