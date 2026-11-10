"""Persistência dos relatos.

- SQLite: local e Docker (arquivo, sem servidor de banco).
- Postgres: deploy serverless (Vercel + Neon). Cada instância da função é independente,
  então os dados precisam ficar num banco compartilhado.

Os dois guardam o relato como documento JSON; a regra de negócio fica na classe base.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.schemas.report import Category, Location, Report, Status


class ReportRepository:
    """Regras comuns. As subclasses só implementam _insert_placeholder, _save e _rows."""

    def _insert_placeholder(self) -> int:
        raise NotImplementedError

    def _save(self, report_id: int, data: str) -> None:
        raise NotImplementedError

    def _rows(self) -> list[dict]:
        raise NotImplementedError

    def add(self, fields: dict) -> Report:
        new_id = self._insert_placeholder()
        now = datetime.now(timezone.utc)
        report = Report(id=new_id, protocol=f"ZLA-{now:%Y%m%d}-{new_id:05d}", created_at=now, **fields)
        self._save(new_id, report.model_dump_json())
        return report

    def list(self, protocols: list[str] | None = None) -> list[Report]:
        reports = [Report.model_validate(row) for row in self._rows()]
        if protocols is not None:
            wanted = set(protocols)
            reports = [r for r in reports if r.protocol in wanted]
        return reports

    def get_by_protocol(self, protocol: str) -> Report | None:
        return next((r for r in self.list() if r.protocol == protocol), None)

    def update(self, report: Report) -> Report:
        self._save(report.id, report.model_dump_json())
        return report

    def set_status(self, protocol: str, status: Status, note: str | None) -> Report | None:
        report = self.get_by_protocol(protocol)
        if report is None:
            return None
        return self.update(report.model_copy(update={"status": status, "manager_note": note}))

    def count_similar_open(self, category: Category, location: Location | None, days: int) -> int:
        """Relatos ainda abertos, da mesma categoria, no mesmo CEP ou bairro, nos últimos `days` dias."""
        if location is None:
            return 0
        since = datetime.now(timezone.utc) - timedelta(days=days)
        open_status = {Status.aberto, Status.em_andamento}

        def same_place(r: Report) -> bool:
            if r.location is None:
                return False
            if r.location.cep == location.cep:
                return True
            return bool(location.neighborhood) and (r.location.neighborhood, r.location.city) == (
                location.neighborhood, location.city)

        return sum(
            1 for r in self.list()
            if r.final_category == category and r.status in open_status and r.created_at >= since and same_place(r)
        )


class SQLiteReportRepository(ReportRepository):
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)")
            self._conn.commit()

    def _insert_placeholder(self) -> int:
        with self._lock:
            cur = self._conn.execute("INSERT INTO reports (data) VALUES ('{}')")
            self._conn.commit()
            return cur.lastrowid

    def _save(self, report_id: int, data: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE reports SET data = ? WHERE id = ?", (data, report_id))
            self._conn.commit()

    def _rows(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM reports ORDER BY id DESC").fetchall()
        return [json.loads(r[0]) for r in rows]


class PostgresReportRepository(ReportRepository):
    """Uma conexão curta por operação: combina com funções serverless e com o pooler do Neon."""

    def __init__(self, url: str):
        import psycopg  # import tardio: só é necessário no deploy com Postgres

        self._psycopg = psycopg
        self._url = url
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS reports (id SERIAL PRIMARY KEY, data JSONB NOT NULL)")

    def _connect(self):
        return self._psycopg.connect(self._url, autocommit=True, connect_timeout=10)

    def _insert_placeholder(self) -> int:
        with self._connect() as conn:
            return conn.execute("INSERT INTO reports (data) VALUES ('{}'::jsonb) RETURNING id").fetchone()[0]

    def _save(self, report_id: int, data: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE reports SET data = %s::jsonb WHERE id = %s", (data, report_id))

    def _rows(self) -> list[dict]:
        with self._connect() as conn:
            return [row[0] for row in conn.execute("SELECT data FROM reports ORDER BY id DESC").fetchall()]


def build_repository(database_url: str, database_path: str) -> ReportRepository:
    if database_url.startswith(("postgres://", "postgresql://")):
        return PostgresReportRepository(database_url)
    if os.getenv("VERCEL"):  # sem Postgres na Vercel, só /tmp é gravável (dados se perdem)
        database_path = "/tmp/zela.db"
    return SQLiteReportRepository(database_path)
