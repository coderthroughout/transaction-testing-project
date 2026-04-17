import re
import time
from typing import Dict, Any

from opentelemetry.trace import StatusCode

from telemetry import get_tracer

SUPPORTED_TOKENS = ["USDC", "USDT", "PYUSD"]
MAX_AMOUNT = 100_000.0

MOCK_WALLET = {
    "USDC": 1_000_000.0,
    "USDT": 500_000.0,
    "PYUSD": 200_000.0,
}

EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def validate(state: Dict[str, Any]) -> Dict[str, Any]:
    tracer = get_tracer()
    start = time.time()

    with tracer.start_as_current_span("step.validator") as span:
        span.set_attribute("step.name", "Validator")

        intent = state.get("intent", {})
        token = intent.get("token")
        amount = intent.get("amount")
        destination = intent.get("destination")

        errors = []

        if not destination or not EVM_ADDRESS_RE.match(str(destination)):
            errors.append(f"Invalid EVM address: '{destination}'")

        if amount is None or not isinstance(amount, (int, float)):
            errors.append("Amount must be a number")
        elif amount <= 0:
            errors.append(f"Amount must be > 0, got {amount}")
        elif amount > MAX_AMOUNT:
            errors.append(f"Amount {amount} exceeds maximum {MAX_AMOUNT}")

        if token not in SUPPORTED_TOKENS:
            errors.append(
                f"Unsupported token '{token}'. Supported: {', '.join(SUPPORTED_TOKENS)}"
            )
        elif amount is not None and isinstance(amount, (int, float)):
            balance = MOCK_WALLET.get(token, 0)
            if amount > balance:
                errors.append(
                    f"Insufficient balance: requested {amount} {token}, wallet has {balance}"
                )

        duration_ms = round((time.time() - start) * 1000)

        if errors:
            error_msg = "; ".join(errors)
            span.set_status(StatusCode.ERROR, error_msg)
            span.set_attribute("output.errors", error_msg)
            return {
                "validation": {"valid": False, "errors": errors},
                "final_status": "FAILED",
                "error_step": "Validator",
                "step_timings": [
                    {
                        "step": "Validator",
                        "status": "✗",
                        "duration_ms": duration_ms,
                        "detail": errors[0],
                    }
                ],
            }

        span.set_attribute("output.valid", True)
        span.set_attribute("output.token", token)
        span.set_attribute("output.amount", float(amount))

        return {
            "validation": {
                "valid": True,
                "token": token,
                "amount": float(amount),
                "destination": destination,
                "balance_remaining": MOCK_WALLET[token] - float(amount),
            },
            "step_timings": [
                {
                    "step": "Validator",
                    "status": "✓",
                    "duration_ms": duration_ms,
                    "detail": f"Balance OK ({MOCK_WALLET[token]} {token} available)",
                }
            ],
        }
