import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from opentelemetry.trace import StatusCode

from telemetry import get_tracer

LOG_FILE = Path(__file__).parent.parent / "transactions.log"


def audit_log(state: Dict[str, Any]) -> Dict[str, Any]:
    tracer = get_tracer()
    start = time.time()

    with tracer.start_as_current_span("step.audit_logger") as span:
        span.set_attribute("step.name", "AuditLogger")

        final_status = state.get("final_status", "UNKNOWN")
        span.set_attribute("output.final_status", final_status)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": state.get("message", ""),
            "final_status": final_status,
            "error_step": state.get("error_step"),
            "intent": state.get("intent"),
            "validation": state.get("validation"),
            "risk": state.get("risk"),
            "execution": state.get("execution"),
        }

        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            span.set_attribute("output.log_file", str(LOG_FILE))
        except Exception as e:
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, str(e))

        duration_ms = round((time.time() - start) * 1000)

        return {
            "audit": {"logged": True, "file": str(LOG_FILE)},
            "step_timings": [
                {
                    "step": "AuditLogger",
                    "status": "✓",
                    "duration_ms": duration_ms,
                    "detail": f"Written to {LOG_FILE.name}",
                }
            ],
        }
