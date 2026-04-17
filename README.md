# omium-txn-demo

Stablecoin transaction processing agent built with LangGraph + Omium SDK.
Tests the full Omium stack: SDK auto-instrumentation, CLI, and dashboard traces.

## Setup

```bash
cd omium-txn-demo
pip install -r requirements.txt
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and OMIUM_API_KEY in .env
```

Get your `OMIUM_API_KEY` from the Omium dashboard → API Keys → Create key.

## Run

### Interactive mode
```bash
python main.py
```

### All 5 demo scenarios
```bash
python main.py --demo
```

### Via Omium CLI (traces show in dashboard)
```bash
omium init --api-key omium_xxx --api-url https://api.omium.ai
omium run main.py --demo
```

## What it tests

| Feature | How |
|---|---|
| Omium SDK `omium.init()` | Initialized in `main.py` |
| `omium.instrument_langgraph()` | Auto-instruments the LangGraph graph |
| Trace spans per step | Each step is a child OTel span |
| Omium CLI `omium run` | `omium run main.py` |
| Omium CLI `omium traces list` | After running, check traces in dashboard |
| Audit log | `transactions.log` written after every tx |
| Retry logic | ExecutionSimulator has 10% RPC timeout chance |
| Claude claude-haiku-4-5-20251001 | IntentParser uses Anthropic API |

## Demo scenarios

1. `Send 500 USDC to 0x742d35Cc6634C0532925a3b8D4C9C4E4F8b3e1a2` → **APPROVED**
2. `Transfer 75000 USDT to 0x9A8f...` → **BLOCKED** by RiskScorer (score 80/100)
3. `Pay 100 USDC to 0xINVALID` → **FAILED** at Validator
4. `send some money to my friend` → **FAILED** at IntentParser
5. `Send 100000 USDC to 0x742d...` → **APPROVED** (at exact max limit)

## After running

```bash
# View traces in CLI
omium traces list --project stablecoin-txn-demo

# View executions
omium list

# Watch dashboard
# → https://app.omium.ai
```
