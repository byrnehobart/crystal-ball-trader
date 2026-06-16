from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from .ledger import Ledger
from .models import AgentView, AssetView


DIRECTION_SIGN = {
    "long": 1.0,
    "buy": 1.0,
    "up": 1.0,
    "short": -1.0,
    "sell": -1.0,
    "down": -1.0,
    "flat": 0.0,
    "none": 0.0,
}


def _validated_probability(value: float) -> float:
    if value < 0.5 or value > 1.0:
        raise ValueError("confidence must be a probability from 0.50 to 1.00")
    return value


def _direction_sign(direction: str) -> float:
    try:
        return DIRECTION_SIGN[direction.lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported direction: {direction}") from exc


def calibrated_confidence(asset: AssetView, view: AgentView, ledger: Ledger) -> tuple[float, dict[str, Any]]:
    raw = _validated_probability(asset.confidence)
    profile = view.risk_profile

    shrunk = 0.5 + (raw - 0.5) * (1.0 - profile.confidence_shrinkage)
    bucket = ledger.calibration_for(raw)
    if not bucket:
        return shrunk, {
            "raw_confidence": raw,
            "calibrated_confidence": shrunk,
            "method": "prior_shrinkage",
            "history_count": 0,
        }

    history_weight = min(0.75, bucket.count / 20.0)
    calibrated = (1.0 - history_weight) * shrunk + history_weight * bucket.hit_rate
    return calibrated, {
        "raw_confidence": raw,
        "calibrated_confidence": calibrated,
        "method": "prior_shrinkage_plus_empirical_bucket",
        "history_count": bucket.count,
        "bucket_hit_rate": bucket.hit_rate,
    }


def size_asset(asset: AssetView, view: AgentView, ledger: Ledger) -> dict[str, Any]:
    sign = _direction_sign(asset.direction)
    if sign == 0.0:
        return {
            "symbol": asset.symbol,
            "direction": asset.direction,
            "leverage": 0.0,
            "notional": 0.0,
            "expected_return_pct": 0.0,
            "volatility_pct": asset.volatility_pct or asset.typical_abs_move_pct,
            "calibration": {
                "raw_confidence": asset.confidence,
                "calibrated_confidence": asset.confidence,
                "method": "flat_view",
                "history_count": 0,
            },
        }

    confidence, calibration = calibrated_confidence(asset, view, ledger)
    typical_move = asset.typical_abs_move_pct / 100.0
    volatility = (asset.volatility_pct or asset.typical_abs_move_pct) / 100.0
    edge = sign * (2.0 * confidence - 1.0) * typical_move

    variance = max(volatility * volatility, 1e-8)
    raw_leverage = edge / (view.risk_profile.risk_aversion * variance)
    asset_cap = min(
        view.risk_profile.max_asset_leverage,
        asset.max_leverage if asset.max_leverage is not None else view.risk_profile.max_asset_leverage,
    )
    leverage = max(-asset_cap, min(asset_cap, raw_leverage))

    return {
        "symbol": asset.symbol,
        "direction": "long" if leverage > 0 else "short" if leverage < 0 else "flat",
        "leverage": leverage,
        "notional": leverage * view.bankroll,
        "expected_return_pct": edge * 100.0,
        "volatility_pct": volatility * 100.0,
        "calibration": calibration,
        "raw_merton_leverage": raw_leverage,
    }


def apply_portfolio_constraints(rows: list[dict[str, Any]], view: AgentView) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gross = sum(abs(row["leverage"]) for row in rows)
    gross_scale = 1.0
    if gross > view.risk_profile.max_gross_leverage:
        gross_scale = view.risk_profile.max_gross_leverage / gross

    loss_scale = 1.0
    stressed_loss = sum(
        max(0.0, abs(row["leverage"]) * (row["volatility_pct"] / 100.0) * 3.0)
        for row in rows
    )
    if stressed_loss > view.risk_profile.max_one_day_loss_pct:
        loss_scale = view.risk_profile.max_one_day_loss_pct / stressed_loss

    scale = min(gross_scale, loss_scale)
    constrained = []
    for row in rows:
        adjusted = dict(row)
        adjusted["leverage"] = row["leverage"] * scale
        adjusted["notional"] = adjusted["leverage"] * view.bankroll
        constrained.append(adjusted)

    return constrained, {
        "gross_leverage_before_constraints": gross,
        "gross_leverage_after_constraints": sum(abs(row["leverage"]) for row in constrained),
        "stress_loss_pct_before_constraints": stressed_loss * 100.0,
        "constraint_scale": scale,
        "gross_scale": gross_scale,
        "loss_scale": loss_scale,
    }


def propose(view: AgentView, ledger: Ledger) -> dict[str, Any]:
    rows = [size_asset(asset, view, ledger) for asset in view.assets]
    rows, constraints = apply_portfolio_constraints(rows, view)
    expected_daily_return = sum(
        row["leverage"] * row["expected_return_pct"] / 100.0 for row in rows
    )
    variance = sum(
        (row["leverage"] * row["volatility_pct"] / 100.0) ** 2 for row in rows
    )
    return {
        "question_id": view.question_id,
        "bankroll": view.bankroll,
        "risk_profile": asdict(view.risk_profile),
        "bets": rows,
        "portfolio": {
            "expected_daily_return_pct": expected_daily_return * 100.0,
            "volatility_pct_independent_assets": math.sqrt(variance) * 100.0,
            **constraints,
        },
        "agent_reasoning_summary": view.agent_reasoning_summary,
    }
