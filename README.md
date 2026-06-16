# Crystal Ball Trader

This repo packages a "System 2" layer for the Crystal Ball trading experiment.

The intended workflow is:

1. A coding agent such as Codex or Claude Code receives Wall Street Journal front pages as image/PDF inputs.
2. The agent converts each front page into text, summarizes the market-relevant news, and forms directional views with confidence levels.
3. This package converts those views into risk-adjusted bets using deterministic sizing rules.
4. After returns are known, this package records outcomes so future confidence estimates can be calibrated against prior performance.

The LLM is responsible for perception and judgment. This repo is responsible for memory, arithmetic, constraints, and bet sizing.

## Decimal Convention

All probabilities, returns, volatility estimates, and loss limits are expressed as decimals. For example, eight percent is `0.08`, not `8.0`.

## Install

```bash
git clone <this-repo-url>
cd crystal-ball-trader
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

No runtime dependencies are required beyond Python 3.10+.

## Run With Codex Or Claude Code

Start Codex or Claude Code in this directory and give it the front-page files as inputs. Ask it to follow [prompts/agent_operator.md](prompts/agent_operator.md).

The agent should:

1. Extract/OCR the front page.
2. Summarize the news that should matter for one-day S&P 500 and 30-year Treasury bond returns.
3. Create an agent-view JSON file matching [examples/agent_view.json](examples/agent_view.json).
4. Run:

```bash
crystal-ball propose examples/agent_view.json
```

The command prints the recommended stock and bond bets as leverage multiples and dollar notionals.

## Agent View Schema

Each `assets` entry asks the LLM for a directional view and confidence. The deterministic engine does the sizing.

```json
{
  "question_id": "example-2008-09-15",
  "bankroll": 1000000,
  "agent_reasoning_summary": "Short summary of the market-relevant news and reasoning.",
  "risk_profile": {
    "risk_aversion": 3.0,
    "max_gross_leverage": 8.0,
    "max_asset_leverage": 5.0,
    "max_one_day_loss": 0.25,
    "confidence_shrinkage": 0.25,
    "calibration_horizon_trades": 10,
    "kelly_fraction": null
  },
  "assets": [
    {
      "symbol": "SPX",
      "direction": "short",
      "confidence": 0.62,
      "typical_abs_move": 0.018,
      "volatility": 0.022,
      "rationale": "Equity-negative macro and credit news."
    }
  ]
}
```

`confidence` is the estimated probability that the direction is correct, from `0.50` to `1.00`.

`typical_abs_move` is the LLM's decimal estimate of the absolute one-day move conditional on this sort of news. If the agent is unsure, it should use conservative values and say so in the reasoning summary.

## Recording Outcomes

After the true returns are known, record outcomes:

```bash
crystal-ball record-outcome examples/outcome.json
```

Outcomes are appended to `.crystal-ball/ledger.jsonl`. Future proposals use this ledger to shrink or adjust confidence based on historical calibration buckets.

## Sizing Logic

For each asset, the engine:

1. Shrinks raw LLM confidence toward `0.50`.
2. Adjusts confidence using prior outcomes in the same confidence bucket when available.
   The update is Bayesian and horizon-aware: `calibration_horizon_trades` acts like the number of prior pseudo-observations. With the default value of `10`, ten comparable realized trades get about as much weight as the initial LLM estimate.
3. Converts confidence and typical move into expected return:

```text
expected_return = direction * (2 * calibrated_confidence - 1) * typical_abs_move
```

4. Computes the full Kelly leverage:

```text
full_kelly_leverage = expected_return / volatility^2
```

5. Applies a Kelly fraction. If `kelly_fraction` is `null`, the engine uses `1 / risk_aversion`, so the default risk profile with risk aversion `3.0` is one-third Kelly.
6. Applies asset, gross leverage, and stressed one-day loss constraints.

This is intentionally deterministic and inspectable. The LLM can argue about direction, confidence, and the appropriate inputs, but it does not get to improvise the final bet size.

The objective is expected compound growth over a short sequence of trades, not raw expected dollars. Raw expected-dollar maximization would often push directly to the leverage cap whenever the estimated edge is positive. Kelly-style sizing instead balances edge against variance, which is the behavior we want over a ten-trade Crystal Ball session.

## Files

- `src/crystal_ball/engine.py`: deterministic sizing logic.
- `src/crystal_ball/ledger.py`: proposal and outcome history.
- `src/crystal_ball/cli.py`: command-line entry point.
- `prompts/agent_operator.md`: instructions for Codex or Claude Code.
- `examples/agent_view.json`: sample LLM-produced view.
- `examples/outcome.json`: sample realized-return record.
