"""Persistência dos relatos em SQLite: cada relato é guardado como documento JSON."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.schemas.report import Category, Location, Report, Status


class ReportRepository:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._execute("CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)")

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _save(self, report: Report) -> Report:
        self._execute("UPDATE reports SET data = ? WHERE id = ?", (report.model_dump_json(), report.id))
        return report

    def add(self, fields: dict) -> Report:
        new_id = self._execute("INSERT INTO reports (data) VALUES ('{}')").lastrowid
        now = datetime.now(UTC)
        return self._save(Report(id=new_id, protocol=f"ZLA-{now:%Y%m%d}-{new_id:05d}", created_at=now, **fields))

    def list(self, protocols: list[str] | None = None) -> list[Report]:
        rows = self._execute("SELECT data FROM reports ORDER BY id DESC").fetchall()
        reports = [Report.model_validate(json.loads(r[0])) for r in rows]
        if protocols is not None:
            wanted = set(protocols)
            reports = [r for r in reports if r.protocol in wanted]
        return reports

    def get_by_protocol(self, protocol: str) -> Report | None:
        return next((r for r in self.list() if r.protocol == protocol), None)

    def update(self, report: Report) -> Report:
        return self._save(report)

    def set_status(self, protocol: str, status: Status, note: str | None) -> Report | None:
        report = self.get_by_protocol(protocol)
        if report is None:
            return None
        return self._save(report.model_copy(update={"status": status, "manager_note": note}))

    def count_similar_open(self, category: Category, location: Location | None, days: int) -> int:
        """Relatos ainda abertos, da mesma categoria, no mesmo CEP ou bairro, nos últimos `days` dias."""
        if location is None:
            return 0
        since = datetime.now(UTC) - timedelta(days=days)
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


def build_repository(database_path: str) -> ReportRepository:
    if os.getenv("VERCEL"):  # na Vercel só /tmp é gravável (os dados não sobrevivem a um novo deploy)
        database_path = "/tmp/zela.db"
    return ReportRepository(database_path)
