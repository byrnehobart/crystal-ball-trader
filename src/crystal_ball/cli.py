from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .engine import propose
from .ledger import Ledger
from .models import AgentView


DEFAULT_LEDGER = Path(".crystal-ball/ledger.jsonl")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def cmd_propose(args: argparse.Namespace) -> None:
    ledger = Ledger(args.ledger)
    view = AgentView.from_dict(_read_json(args.input))
    proposal = propose(view, ledger)
    ledger.append({
        "type": "proposal",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proposal": proposal,
    })
    _print_json(proposal)


def cmd_record_outcome(args: argparse.Namespace) -> None:
    ledger = Ledger(args.ledger)
    outcome = _read_json(args.input)
    now = datetime.now(timezone.utc).isoformat()
    for item in outcome["assets"]:
        direction = str(item["direction"]).lower()
        actual_return = float(item["actual_return"])
        if direction in {"long", "buy", "up"}:
            correct = actual_return > 0
        elif direction in {"short", "sell", "down"}:
            correct = actual_return < 0
        else:
            correct = None
        ledger.append({
            "type": "outcome",
            "created_at": now,
            "question_id": outcome["question_id"],
            "symbol": item["symbol"],
            "direction": direction,
            "confidence": float(item["confidence"]),
            "actual_return": actual_return,
            "direction_correct": correct,
        })
    _print_json({"ok": True, "recorded": len(outcome["assets"]), "ledger": str(args.ledger)})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crystal-ball",
        description="Convert LLM directional views into risk-adjusted Crystal Ball bets.",
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    sub = parser.add_subparsers(dest="command", required=True)

    propose_parser = sub.add_parser("propose", help="Generate risk-adjusted bets from an agent view JSON file.")
    propose_parser.add_argument("input", type=Path)
    propose_parser.set_defaults(func=cmd_propose)

    outcome_parser = sub.add_parser("record-outcome", help="Record realized returns for calibration.")
    outcome_parser.add_argument("input", type=Path)
    outcome_parser.set_defaults(func=cmd_record_outcome)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
