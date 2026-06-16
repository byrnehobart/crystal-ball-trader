from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AssetView:
    symbol: str
    direction: str
    confidence: float
    typical_abs_move_pct: float
    volatility_pct: float | None = None
    max_leverage: float | None = None
    rationale: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssetView":
        return cls(
            symbol=str(data["symbol"]),
            direction=str(data["direction"]).lower(),
            confidence=float(data["confidence"]),
            typical_abs_move_pct=float(data["typical_abs_move_pct"]),
            volatility_pct=(
                float(data["volatility_pct"])
                if data.get("volatility_pct") is not None
                else None
            ),
            max_leverage=(
                float(data["max_leverage"])
                if data.get("max_leverage") is not None
                else None
            ),
            rationale=str(data.get("rationale", "")),
        )


@dataclass(frozen=True)
class RiskProfile:
    risk_aversion: float = 3.0
    max_gross_leverage: float = 8.0
    max_asset_leverage: float = 5.0
    max_one_day_loss_pct: float = 0.25
    confidence_shrinkage: float = 0.25

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RiskProfile":
        if not data:
            return cls()
        return cls(
            risk_aversion=float(data.get("risk_aversion", cls.risk_aversion)),
            max_gross_leverage=float(data.get("max_gross_leverage", cls.max_gross_leverage)),
            max_asset_leverage=float(data.get("max_asset_leverage", cls.max_asset_leverage)),
            max_one_day_loss_pct=float(data.get("max_one_day_loss_pct", cls.max_one_day_loss_pct)),
            confidence_shrinkage=float(data.get("confidence_shrinkage", cls.confidence_shrinkage)),
        )


@dataclass(frozen=True)
class AgentView:
    question_id: str
    bankroll: float
    assets: list[AssetView]
    risk_profile: RiskProfile = field(default_factory=RiskProfile)
    agent_reasoning_summary: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentView":
        return cls(
            question_id=str(data["question_id"]),
            bankroll=float(data.get("bankroll", 1_000_000)),
            assets=[AssetView.from_dict(item) for item in data["assets"]],
            risk_profile=RiskProfile.from_dict(data.get("risk_profile")),
            agent_reasoning_summary=str(data.get("agent_reasoning_summary", "")),
        )
