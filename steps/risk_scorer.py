import time
from typing import Dict, Any

from opentelemetry.trace import StatusCode

from telemetry import get_tracer


def score_risk(state: Dict[str, Any]) -> Dict[str, Any]:
    tracer = get_tracer()
    start = time.time()

    with tracer.start_as_current_span("step.risk_scorer") as span:
        span.set_attribute("step.name", "RiskScorer")

        validation = state.get("validation", {})
        amount = validation.get("amount", 0)
        destination = validation.get("destination", "")

        score = 0
        reasons = []

        if amount > 50_000:
            score += 60
            reasons.append(f"Very large amount ({amount}): +60")
        elif amount > 10_000:
            score += 30
            reasons.append(f"Large amount ({amount}): +30")
        elif amount > 1_000:
            score += 10
            reasons.append(f"Moderate amount ({amount}): +10")

        if destination and not (
            destination.lower().startswith("0x1")
            or destination.lower().startswith("0x7")
        ):
            score += 20
            reasons.append("Unknown address pattern: +20")

        span.set_attribute("output.risk_score", score)
        span.set_attribute("output.reasons", "; ".join(reasons) if reasons else "none")

        duration_ms = round((time.time() - start) * 1000)

        if score > 70:
            block_reason = f"Risk score {score}/100 exceeds threshold (70). Triggers: {'; '.join(reasons)}"
            span.set_status(StatusCode.ERROR, block_reason)
            return {
                "risk": {"score": score, "blocked": True, "reasons": reasons},
                "final_status": "BLOCKED",
                "error_step": "RiskScorer",
                "step_timings": [
                    {
                        "step": "RiskScorer",
                        "status": "✗",
                        "duration_ms": duration_ms,
                        "detail": f"Score {score}/100 — BLOCKED",
                    }
                ],
            }

        return {
            "risk": {"score": score, "blocked": False, "reasons": reasons},
            "step_timings": [
                {
                    "step": "RiskScorer",
                    "status": "✓",
                    "duration_ms": duration_ms,
                    "detail": f"Score {score}/100 — cleared",
                }
            ],
        }
