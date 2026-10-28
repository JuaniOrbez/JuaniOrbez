"""Registro de ofertas vistas y su estado, en output/tracker.json."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

STATES = ["nueva", "descartada", "adaptada", "postulada", "entrevista", "rechazada", "oferta"]


class Tracker:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, dict] = json.loads(path.read_text()) if path.exists() else {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def seen(self, job_id: str) -> bool:
        return job_id in self.data

    def upsert(self, job_id: str, **fields) -> None:
        entry = self.data.setdefault(job_id, {"state": "nueva", "first_seen": date.today().isoformat()})
        entry.update({k: v for k, v in fields.items() if v is not None})
        entry["updated"] = date.today().isoformat()

    def set_state(self, job_id: str, state: str) -> None:
        if state not in STATES:
            raise ValueError(f"Estado inválido. Opciones: {', '.join(STATES)}")
        if job_id not in self.data:
            raise KeyError(f"No conozco la oferta {job_id}")
        self.upsert(job_id, state=state)
