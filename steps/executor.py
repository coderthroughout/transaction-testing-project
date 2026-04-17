import hashlib
import random
import time
from datetime import datetime, timezone
from typing import Dict, Any

from opentelemetry.trace import StatusCode

from telemetry import get_tracer


class RPCTimeoutError(Exception):
    pass


def _simulate_transaction(destination: str, amount: float, token: str) -> Dict:
    raw = f"{destination}{amount}{token}{datetime.now(timezone.utc).isoformat()}"
    tx_hash = "0x" + hashlib.sha256(raw.encode()).hexdigest()
    latency = random.uniform(0.1, 0.8)
    time.sleep(latency)

    if random.random() < 0.10:
        raise RPCTimeoutError("RPC node timeout: connection refused after 30s")

    gas = random.randint(21_000, 65_000)
    confirmation_time = round(random.uniform(1.5, 15.0), 1)
    return {
        "tx_hash": tx_hash,
        "gas_estimate": gas,
        "confirmation_time_s": confirmation_time,
        "latency_ms": round(latency * 1000),
    }


def execute_transaction(state: Dict[str, Any]) -> Dict[str, Any]:
    tracer = get_tracer()
    start = time.time()

    validation = state.get("validation", {})
    destination = validation.get("destination", "")
    amount = validation.get("amount", 0)
    token = validation.get("token", "")

    with tracer.start_as_current_span("step.executor") as span:
        span.set_attribute("step.name", "ExecutionSimulator")
        span.set_attribute("input.destination", destination)
        span.set_attribute("input.amount", amount)
        span.set_attribute("input.token", token)

        retry_count = 0
        last_error = None

        for attempt in range(2):
            try:
                if attempt > 0:
                    time.sleep(0.5)
                    retry_count = attempt
                    span.set_attribute("retry_count", retry_count)

                result = _simulate_transaction(destination, amount, token)
                duration_ms = round((time.time() - start) * 1000)

                span.set_attribute("output.tx_hash", result["tx_hash"][:20] + "...")
                span.set_attribute("output.gas_estimate", result["gas_estimate"])
                span.set_attribute("output.confirmation_time_s", result["confirmation_time_s"])
                if retry_count > 0:
                    span.set_attribute("output.retried", True)

                detail = f"tx {result['tx_hash'][:12]}... gas={result['gas_estimate']}"
                if retry_count:
                    detail += f" (retried {retry_count}x)"

                return {
                    "execution": {**result, "retry_count": retry_count, "success": True},
                    "final_status": "APPROVED",
                    "step_timings": [
                        {
                            "step": "ExecutionSimulator",
                            "status": "✓",
                            "duration_ms": duration_ms,
                            "detail": detail,
                        }
                    ],
                }

            except RPCTimeoutError as e:
                last_error = e
                span.add_event(f"attempt_{attempt + 1}_timeout", {"error": str(e)})

        duration_ms = round((time.time() - start) * 1000)
        span.record_exception(last_error)
        span.set_status(StatusCode.ERROR, str(last_error))
        span.set_attribute("retry_count", retry_count)

        return {
            "execution": {"success": False, "error": str(last_error), "retry_count": retry_count},
            "final_status": "FAILED",
            "error_step": "ExecutionSimulator",
            "step_timings": [
                {
                    "step": "ExecutionSimulator",
                    "status": "✗",
                    "duration_ms": duration_ms,
                    "detail": f"RPC timeout after {retry_count + 1} attempt(s)",
                }
            ],
        }
