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
            "calibration_horizon_trades": profile.calibration_horizon_trades,
        }

    prior_strength = max(1.0, profile.calibration_horizon_trades)
    history_weight = bucket.count / (prior_strength + bucket.count)
    calibrated = (1.0 - history_weight) * shrunk + history_weight * bucket.hit_rate
    return calibrated, {
        "raw_confidence": raw,
        "calibrated_confidence": calibrated,
        "method": "ten_trade_bayesian_update",
        "history_count": bucket.count,
        "bucket_hit_rate": bucket.hit_rate,
        "history_weight": history_weight,
        "calibration_horizon_trades": profile.calibration_horizon_trades,
    }


def size_asset(asset: AssetView, view: AgentView, ledger: Ledger) -> dict[str, Any]:
    sign = _direction_sign(asset.direction)
    if sign == 0.0:
        return {
            "symbol": asset.symbol,
            "direction": asset.direction,
            "leverage": 0.0,
            "notional": 0.0,
            "expected_return": 0.0,
            "volatility": asset.volatility or asset.typical_abs_move,
            "calibration": {
                "raw_confidence": asset.confidence,
                "calibrated_confidence": asset.confidence,
                "method": "flat_view",
                "history_count": 0,
            },
        }

    confidence, calibration = calibrated_confidence(asset, view, ledger)
    typical_move = asset.typical_abs_move
    volatility = asset.volatility or asset.typical_abs_move
    edge = sign * (2.0 * confidence - 1.0) * typical_move

    variance = max(volatility * volatility, 1e-8)
    full_kelly_leverage = edge / variance
    kelly_fraction = (
        view.risk_profile.kelly_fraction
        if view.risk_profile.kelly_fraction is not None
        else 1.0 / view.risk_profile.risk_aversion
    )
    raw_leverage = full_kelly_leverage * kelly_fraction
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
        "expected_return": edge,
        "volatility": volatility,
        "calibration": calibration,
        "full_kelly_leverage": full_kelly_leverage,
        "kelly_fraction": kelly_fraction,
        "raw_fractional_kelly_leverage": raw_leverage,
    }


def apply_portfolio_constraints(rows: list[dict[str, Any]], view: AgentView) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gross = sum(abs(row["leverage"]) for row in rows)
    gross_scale = 1.0
    if gross > view.risk_profile.max_gross_leverage:
        gross_scale = view.risk_profile.max_gross_leverage / gross

    loss_scale = 1.0
    stressed_loss = sum(
        max(0.0, abs(row["leverage"]) * row["volatility"] * 3.0)
        for row in rows
    )
    if stressed_loss > view.risk_profile.max_one_day_loss:
        loss_scale = view.risk_profile.max_one_day_loss / stressed_loss

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
        "stress_loss_before_constraints": stressed_loss,
        "constraint_scale": scale,
        "gross_scale": gross_scale,
        "loss_scale": loss_scale,
    }


def propose(view: AgentView, ledger: Ledger) -> dict[str, Any]:
    rows = [size_asset(asset, view, ledger) for asset in view.assets]
    rows, constraints = apply_portfolio_constraints(rows, view)
    expected_daily_return = sum(
        row["leverage"] * row["expected_return"] for row in rows
    )
    variance = sum(
        (row["leverage"] * row["volatility"]) ** 2 for row in rows
    )
    return {
        "question_id": view.question_id,
        "bankroll": view.bankroll,
        "risk_profile": asdict(view.risk_profile),
        "bets": rows,
        "portfolio": {
            "expected_daily_return": expected_daily_return,
            "volatility_independent_assets": math.sqrt(variance),
            **constraints,
        },
        "agent_reasoning_summary": view.agent_reasoning_summary,
    }
