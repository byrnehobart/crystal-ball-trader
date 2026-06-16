from pathlib import Path

from crystal_ball.engine import propose
from crystal_ball.ledger import Ledger
from crystal_ball.models import AgentView


def test_propose_respects_constraints(tmp_path: Path) -> None:
    view = AgentView.from_dict(
        {
            "question_id": "test",
            "bankroll": 1_000_000,
            "risk_profile": {
                "risk_aversion": 3,
                "max_gross_leverage": 4,
                "max_asset_leverage": 3,
                "max_one_day_loss_pct": 0.2,
            },
            "assets": [
                {
                    "symbol": "SPX",
                    "direction": "long",
                    "confidence": 0.7,
                    "typical_abs_move_pct": 2,
                    "volatility_pct": 2,
                },
                {
                    "symbol": "USBOND30Y",
                    "direction": "short",
                    "confidence": 0.65,
                    "typical_abs_move_pct": 1,
                    "volatility_pct": 1,
                },
            ],
        }
    )
    result = propose(view, Ledger(tmp_path / "ledger.jsonl"))
    gross = sum(abs(row["leverage"]) for row in result["bets"])
    assert gross <= 4.000001
    assert result["portfolio"]["constraint_scale"] <= 1.0


def test_ledger_calibration_changes_confidence(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    for idx in range(10):
        ledger.append(
            {
                "type": "outcome",
                "question_id": f"q{idx}",
                "symbol": "SPX",
                "direction": "long",
                "confidence": 0.6,
                "actual_return_pct": -1.0,
                "direction_correct": False,
            }
        )
    view = AgentView.from_dict(
        {
            "question_id": "test",
            "bankroll": 1_000_000,
            "assets": [
                {
                    "symbol": "SPX",
                    "direction": "long",
                    "confidence": 0.6,
                    "typical_abs_move_pct": 2,
                    "volatility_pct": 2,
                }
            ],
        }
    )
    result = propose(view, ledger)
    calibration = result["bets"][0]["calibration"]
    assert calibration["method"] == "prior_shrinkage_plus_empirical_bucket"
    assert calibration["calibrated_confidence"] < calibration["raw_confidence"]
