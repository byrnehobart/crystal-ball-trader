from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CalibrationBucket:
    count: int
    hit_rate: float


class Ledger:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def append(self, row: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def calibration_for(self, confidence: float) -> CalibrationBucket | None:
        rows = [row for row in self.read() if row.get("type") == "outcome"]
        low = max(0.5, confidence - 0.05)
        high = min(1.0, confidence + 0.05)
        matching = [
            row
            for row in rows
            if low <= float(row.get("confidence", 0.0)) <= high
            and row.get("direction_correct") is not None
        ]
        if not matching:
            return None
        hits = sum(1 for row in matching if bool(row["direction_correct"]))
        return CalibrationBucket(count=len(matching), hit_rate=hits / len(matching))
