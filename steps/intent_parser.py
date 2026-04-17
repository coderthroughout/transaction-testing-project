import json
import os
import re
import time
from typing import Dict, Any

from openai import OpenAI
from opentelemetry.trace import StatusCode

from telemetry import get_tracer

SYSTEM_PROMPT = """You are a stablecoin transaction parser. Extract transaction details from natural language messages.

Return ONLY a valid JSON object with exactly these fields:
- "token": string — one of "USDC", "USDT", "PYUSD", or null if not found
- "amount": number (float) — the numeric amount, or null if not found
- "destination": string — the destination Ethereum address (0x...), or null if not found
- "error": string or null — if the input is ambiguous, incomplete, or cannot be parsed, set a clear error message; otherwise null

Examples:
Input: "Send 500 USDC to 0x742d35Cc6634C0532925a3b8D4C9C4E4F8b3e1a2"
Output: {"token": "USDC", "amount": 500.0, "destination": "0x742d35Cc6634C0532925a3b8D4C9C4E4F8b3e1a2", "error": null}

Input: "send some money to my friend"
Output: {"token": null, "amount": null, "destination": null, "error": "Missing required fields: token, amount, and destination address are all unspecified"}

Return ONLY the JSON object. No explanation, no markdown, no code blocks."""


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["DO_API_KEY"],
        base_url=os.environ.get("DO_INFERENCE_BASE_URL", "https://inference.do-ai.run/v1"),
    )


def parse_intent(state: Dict[str, Any]) -> Dict[str, Any]:
    tracer = get_tracer()
    start = time.time()

    with tracer.start_as_current_span("step.intent_parser") as span:
        span.set_attribute("step.name", "IntentParser")
        span.set_attribute("input.message", state["message"])

        try:
            client = _get_client()
            model = os.environ.get("DO_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")

            response = client.chat.completions.create(
                model=model,
                max_tokens=256,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": state["message"]},
                ],
                temperature=0.0,
            )

            raw = response.choices[0].message.content.strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            result = json.loads(match.group()) if match else json.loads(raw)

            duration_ms = round((time.time() - start) * 1000)

            if result.get("error"):
                span.set_status(StatusCode.ERROR, result["error"])
                span.set_attribute("output.error", result["error"])
                return {
                    "intent": result,
                    "final_status": "FAILED",
                    "error_step": "IntentParser",
                    "step_timings": [
                        {
                            "step": "IntentParser",
                            "status": "✗",
                            "duration_ms": duration_ms,
                            "detail": result["error"],
                        }
                    ],
                }

            span.set_attribute("output.token", str(result.get("token")))
            span.set_attribute("output.amount", str(result.get("amount")))
            dest = str(result.get("destination", ""))
            span.set_attribute("output.destination_prefix", dest[:10])

            return {
                "intent": result,
                "step_timings": [
                    {
                        "step": "IntentParser",
                        "status": "✓",
                        "duration_ms": duration_ms,
                        "detail": f"{result.get('token')} {result.get('amount')} → {dest[:12]}...",
                    }
                ],
            }

        except Exception as e:
            duration_ms = round((time.time() - start) * 1000)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, str(e))
            return {
                "intent": {"error": str(e)},
                "final_status": "FAILED",
                "error_step": "IntentParser",
                "step_timings": [
                    {
                        "step": "IntentParser",
                        "status": "✗",
                        "duration_ms": duration_ms,
                        "detail": str(e),
                    }
                ],
            }
