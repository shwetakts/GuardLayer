# GuardLayer — Cross-Provider Guardrail Policy Engine

GuardLayer enforces LLM governance policies defined once in YAML and applies them consistently across multiple LLM providers. Input and output content is checked for PII, toxicity, and banned topics before reaching the provider and again before reaching the user. Every request is audited with a sanitized, PII-redacted record. No raw PII is ever stored.

---

## Table of Contents

1. [What GuardLayer Does](#1-what-guardlayer-does)
2. [Architecture & Request Flow](#2-architecture--request-flow)
3. [Project Structure](#3-project-structure)
4. [Installation](#4-installation)
5. [Configuration](#5-configuration)
6. [Local & Provider Model Requirements](#6-local--provider-model-requirements)
7. [Running the Application](#7-running-the-application)
8. [Running the Demo](#8-running-the-demo)
9. [What the Demo Demonstrates](#9-what-the-demo-demonstrates)
10. [Audit Logging & Structured Request Context](#10-audit-logging--structured-request-context)
11. [PII Detection & HF NER Fallback](#11-pii-detection--hf-ner-fallback)
12. [Testing](#12-testing)
13. [Current Limitations & Development Notes](#13-current-limitations--development-notes)

---

## 1. What GuardLayer Does

An enterprise that uses multiple LLM providers faces a fragmented governance problem: each provider has its own (or no) native safety controls, requiring duplicated, provider-specific policy implementations.

GuardLayer solves this with a single policy engine sitting in front of all providers:

- **Define once** — governance rules (PII redaction, toxicity thresholds, denied topics) are written in a single YAML policy file.
- **Enforce everywhere** — the same `GuardEngine` runs those rules against every request and response, regardless of provider.
- **Audit uniformly** — every interaction is written to a SQLite audit log with an identical schema across providers, with PII redacted before storage.
- **Inherit safely** — child policies can extend a base policy but cannot weaken it (cannot lower toxicity thresholds, cannot remove denied topics, cannot demote block to allow).

---

## 2. Architecture & Request Flow

```
Client
  │
  ▼
POST /chat  (FastAPI)
  │  Sets request_id / session_id / agent_id in logging context (contextvars)
  │
  ▼
Policy Loader
  │  Loads & merges YAML policy; hashes effective policy for versioning
  │
  ▼
GuardEngine.check_input(text, policy)
  ├── PIIDetector   → regex (email, phone, credit-card/Luhn) + optional HF NER (PERSON, ORG, LOC)
  ├── ToxicityScorer→ optional HF text-classification model; falls back to TF-IDF + LogisticRegression
  └── TopicDenier   → keyword matching + optional sentence-transformers cosine similarity
  │
  │  If BLOCK → write audit (called_provider=False) → return 200 blocked response
  │  If REDACT → replace PII spans in message before forwarding
  │
  ▼
ProviderRouter → selects adapter by provider name
  ├── MockOpenAIAdapter   (test/demo — deterministic responses)
  ├── MockAnthropicAdapter(test/demo — deterministic responses)
  ├── OllamaProvider      (real local inference via Ollama OpenAI-compatible endpoint)
  └── [custom adapters]   (register at runtime via router.register())
  │
  ▼
GuardEngine.check_output(response, policy)
  ├── PIIDetector   → same pipeline as input
  ├── ToxicityScorer
  └── TopicDenier
  │
  │  If BLOCK → "Response blocked by safety policy."
  │  If REDACT → replace PII spans in response text
  │
  ▼
AuditLogger.log(...)
  │  PIIDetector.redact() run on input/output before INSERT
  │  Writes to SQLiteAuditRepository via AuditRepository protocol
  │
  ▼
ChatResponse → returned to client
  (request_id, audit_id, provider, model, final_action, blocked_rules)
```

All log lines emitted during a request carry `request_id`, `session_id`, and `agent_id` via Python `contextvars` — no manual threading is required.

---

## 3. Project Structure

```
C:\GuardLayer\
│
├── app\
│   ├── config.py          # pydantic-settings; all env-var configuration
│   ├── dependencies.py    # FastAPI Depends factories (engine, router, audit)
│   └── main.py            # FastAPI app, /chat /health /policy /audit endpoints
│
├── core\
│   ├── checks\
│   │   ├── pii_detector.py     # Regex + optional HF NER (lazy-loaded)
│   │   ├── topic_denier.py     # Keyword + optional sentence-transformers similarity
│   │   └── toxicity_scorer.py  # Optional HF classifier; fallback to TF-IDF/LogReg
│   ├── exceptions.py           # ProviderTimeoutError, ProviderUnavailableError
│   ├── guard_engine.py         # check_input / check_output orchestration
│   ├── logging_context.py      # contextvars, ContextFilter, JSONFormatter, setup_logging
│   ├── models.py               # Pydantic models (Policy, PolicyRule, ChatRequest, …)
│   └── policy_loader.py        # YAML load, extends/merge, inheritance safety checks
│
├── providers\
│   ├── base.py                 # BaseProviderAdapter (async generate interface)
│   ├── mock_openai.py          # Deterministic mock for tests and demo
│   ├── mock_anthropic.py       # Deterministic mock for tests and demo
│   ├── mock_third.py           # Extensibility demonstration adapter
│   ├── ollama.py               # Real local Ollama provider (httpx, async)
│   └── router.py               # ProviderRouter: name → adapter dispatch
│
├── storage\
│   ├── base.py                 # AuditRepository Protocol (interface)
│   ├── sqlite_repository.py    # SQLiteAuditRepository implementation
│   └── audit_logger.py         # AuditLogger: PII-redacts then delegates to repository
│
├── policy\
│   ├── base_policy.yaml        # Root governance policy (cannot be weakened by children)
│   └── policy.yaml             # Active child policy (extends base_policy.yaml)
│
├── tests\                      # pytest test suite (16 files, phases 1–7 + integration)
├── data\                       # SQLite audit DB written here at runtime
├── demo.py                     # End-to-end demonstration script
├── requirements.txt
└── README.md
```

---

## 4. Installation

Requires **Python 3.11+** and **Windows PowerShell** (paths use `\`).

```powershell
cd C:\GuardLayer

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt
```

`requirements.txt` installs:

| Package | Purpose |
|---|---|
| `fastapi` + `uvicorn` | API server |
| `pydantic` + `pydantic-settings` | Models and configuration |
| `pyyaml` | Policy file parsing |
| `scikit-learn` | TF-IDF / LogisticRegression fallback toxicity scorer |
| `httpx` | Async HTTP client for Ollama provider |
| `sentence-transformers` | Semantic topic similarity (lazy-loaded; optional) |
| `pytest` + `anyio` | Test runner |

> **Hugging Face models** (`transformers`, `torch`) are **not** in `requirements.txt`. Install them separately only if you intend to enable `USE_HF_TOXICITY=True` or `USE_HF_PII_NER=True` (see §6).

---

## 5. Configuration

All configuration is read from environment variables (or a `.env` file). Defaults are safe for local development without any API keys.

| Variable | Default | Description |
|---|---|---|
| `GUARDLAYER_POLICY_PATH` | `C:\GuardLayer\policy\policy.yaml` | Active policy file |
| `GUARDLAYER_DB_PATH` | `C:\GuardLayer\data\audit.db` | SQLite database path (legacy; also sets DATABASE_URL) |
| `GUARDLAYER_DATABASE_URL` | `sqlite:///C:\GuardLayer\data\audit.db` | Full SQLite URL used by the audit repository |
| `GUARDLAYER_LOG_LEVEL` | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `GUARDLAYER_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `GUARDLAYER_OLLAMA_MODEL` | `llama2` | Ollama model name |
| `GUARDLAYER_PROVIDER_TIMEOUT` | `60` | Provider HTTP timeout in seconds |
| `GUARDLAYER_EMBEDDING_MODEL_NAME` | `all-MiniLM-L6-v2` | sentence-transformers model for topic similarity |
| `USE_HF_TOXICITY` | `False` | Enable real HF toxicity classifier (requires `transformers`) |
| `GUARDLAYER_TOXICITY_MODEL_NAME` | `Hate-speech-CNERG/dehatebert-mono-english` | HF model for toxicity |
| `USE_HF_PII_NER` | `False` | Enable real HF NER for PERSON/ORG/LOC detection (requires `transformers`) |
| `GUARDLAYER_PII_NER_MODEL_NAME` | `dslim/distilbert-NER` | HF model for NER PII |

**Both HF flags default to `False`.** No model is downloaded unless you explicitly set them to `True` and have `transformers` and `torch` installed.

---

## 6. Local & Provider Model Requirements

### Mock providers (default, no download)
`mock_openai`, `mock_anthropic`, and `mock_third` return deterministic responses. They are the default providers used in tests and the demo. No API keys or network access required.

### Ollama (real local inference, no API key)
1. Install Ollama from [https://ollama.com](https://ollama.com).
2. Pull a model: `ollama pull llama2` (or whichever model you set in `OLLAMA_MODEL`).
3. Ensure the server is running: `ollama serve`.
4. Set `provider: "ollama"` in your `/chat` request body.

### Hugging Face toxicity model (`USE_HF_TOXICITY=True`)
```powershell
pip install transformers torch
$env:USE_HF_TOXICITY = "True"
```
First call will download `Hate-speech-CNERG/dehatebert-mono-english` (~268 MB) to the local HF cache. Subsequent calls use the cached model. CPU inference only.

### Hugging Face NER model (`USE_HF_PII_NER=True`)
```powershell
pip install transformers torch
$env:USE_HF_PII_NER = "True"
```
First call will download `dslim/distilbert-NER` to the local HF cache. CPU inference only.

### sentence-transformers (semantic topic detection)
`sentence-transformers` is already in `requirements.txt`. The `all-MiniLM-L6-v2` model (~80 MB) is downloaded on first use when a policy rule sets `semantic_threshold`. It is **not** loaded on startup.

---

## 7. Running the Application

```powershell
cd C:\GuardLayer
.venv\Scripts\activate
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`.  
Interactive Swagger docs: `http://127.0.0.1:8000/docs`

### Example: clean request
```powershell
curl -X POST http://127.0.0.1:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"provider":"openai","messages":[{"role":"user","content":"How does gravity work?"}]}'
```

### Example: PII in response (will be redacted)
```powershell
curl -X POST http://127.0.0.1:8000/chat `
  -H "Content-Type: application/json" `
  -d '{"provider":"openai","messages":[{"role":"user","content":"trigger pii"}]}'
```

### Example: query audit log
```powershell
curl http://127.0.0.1:8000/audit?provider=openai
```

---

## 8. Running the Demo

```powershell
cd C:\GuardLayer
.venv\Scripts\activate
python demo.py
```

The demo runs entirely in-process using FastAPI's `TestClient`. No server needs to be running. No model downloads are triggered — both `USE_HF_TOXICITY` and `USE_HF_PII_NER` are forced to `False` at the start of the script, and NER PII detection is demonstrated using an injected mock pipeline.

---

## 9. What the Demo Demonstrates

The demo walks through all eight success criteria and prints a pass/fail summary:

| # | Criterion |
|---|---|
| SC-1 | PII (email, phone) in mock LLM output is redacted consistently across OpenAI and Anthropic providers |
| SC-2 | Toxic input is blocked **before** the provider is called (`called_provider=False` in the audit) |
| SC-3 | Audit records for OpenAI, Anthropic, and the custom third provider have an identical schema |
| SC-4 | A third provider adapter registered at runtime is immediately covered by the same guardrail policy |
| SC-5 | A request containing a denied topic (`credential theft`) is blocked on input |
| SC-6 | A child policy attempting to weaken a parent toxicity threshold is rejected at load time with `ValueError` |
| SC-7 | NER-based PII detection (injected mock pipeline) correctly detects `PERSON` entities and redacts them |
| SC-8 | A caller-supplied `request_id` is echoed in the response and persisted in the audit record alongside `session_id` and `agent_id` |

---

## 10. Audit Logging & Structured Request Context

### Audit record fields

Every request writes one row to `data/audit.db` (table: `audits`):

| Field | Description |
|---|---|
| `audit_id` | UUID primary key |
| `timestamp` | ISO-8601 UTC |
| `provider` | LLM provider name (e.g. `openai`, `ollama`) |
| `request_id` | Caller-supplied or auto-generated UUID |
| `session_id` | Optional session context |
| `agent_id` | Optional agent context |
| `policy_version` | SHA-256 of the effective merged policy |
| `input_check_result` | JSON: allowed, matched_rules, action, findings |
| `output_check_result` | JSON: same structure; null if provider was not called |
| `final_action` | `allow`, `redact`, or `block` |
| `latency_ms` | Total wall time for the request |
| `called_provider` | `1` if the provider was reached; `0` if blocked before the call |
| `input_text` | PII-redacted copy of the last user message |
| `output_text` | PII-redacted copy of the provider response |

**PII governance:** `AuditLogger.log()` runs `PIIDetector.redact()` on both `input_text` and `output_text` before any SQL write. Raw PII is never stored in the database.

### Structured JSON logging

All application log lines are emitted as JSON. Each log record automatically includes the current request context:

```json
{
  "timestamp": "2026-08-12T08:30:01.123Z",
  "level": "INFO",
  "logger": "app.main",
  "message": "Policy loaded. Version hash: a3b4c5...",
  "request_id": "c1d2e3f4-...",
  "session_id": "sess-xyz",
  "agent_id": "agent-v1"
}
```

Context variables are set at the start of each `/chat` request and reset in a `finally` block, so they never leak between concurrent requests.

---

## 11. PII Detection & HF NER Fallback

PII detection runs in two stages:

**Stage 1 — Regex (always active):**
- Email: RFC-5321 pattern
- Phone: common US formats with negative lookaround to avoid numeric false positives
- Credit card: digit-sequence pattern validated with the Luhn checksum algorithm

**Stage 2 — HF NER (opt-in, lazy-loaded):**
- Detects `PERSON`, `ORG`, and `LOCATION` entities using a local `dslim/distilbert-NER` model
- Only activated when `USE_HF_PII_NER=True`
- Model is loaded on the **first request that reaches the NER stage**, not at startup
- If the model fails to load or inference throws, the detector silently falls back to regex-only behaviour
- A mock pipeline can be injected via `PIIDetector.set_pipeline(pipe)` for tests — this prevents any model download

**Fallback states:**

| `USE_HF_PII_NER` | `PIIDetector.pipeline` value | Behaviour |
|---|---|---|
| `False` (default) | `"FALLBACK"` | Regex only; no import of `transformers` |
| `True` | real pipeline object | NER + regex |
| `True`, model fails to load | `"FALLBACK"` | Regex only; warning logged |
| any | injected mock | Mock NER + regex (used in tests) |

---

## 12. Testing

All tests are in `tests/`. Run from the project root with the virtual environment active.

```powershell
# Full test suite
.venv\Scripts\python.exe -m pytest tests -v

# Individual phase tests
.venv\Scripts\python.exe -m pytest tests/test_phase1.py -v
.venv\Scripts\python.exe -m pytest tests/test_phase2.py -v
.venv\Scripts\python.exe -m pytest tests/test_phase3.py -v
.venv\Scripts\python.exe -m pytest tests/test_phase4.py -v
.venv\Scripts\python.exe -m pytest tests/test_phase5.py -v
.venv\Scripts\python.exe -m pytest tests/test_phase6.py -v
.venv\Scripts\python.exe -m pytest tests/test_phase7.py -v

# Integration tests
.venv\Scripts\python.exe -m pytest tests/test_integration.py -v

# Specific component tests
.venv\Scripts\python.exe -m pytest tests/test_guard_engine.py tests/test_pii.py tests/test_policy.py -v
```

**No test downloads any model.** Phase 4 and Phase 5 tests inject mock pipelines via `set_pipeline()`. Phase 3 tests that exercise semantic similarity use the `sentence-transformers` package but only if the model is already cached.

---

## 13. Current Limitations & Development Notes

### Provider adapters
`mock_openai`, `mock_anthropic`, and `mock_third` are **deterministic test doubles**, not SDK wrappers. They return hardcoded responses designed to exercise guardrail paths (clean text, PII-containing text, etc.). To use real providers, implement `BaseProviderAdapter.generate()` with the provider's SDK and register the adapter in `app/dependencies.py`.

The `OllamaProvider` (`providers/ollama.py`) is a **real implementation** using `httpx.AsyncClient` against Ollama's OpenAI-compatible endpoint. It requires a running Ollama server.

### Toxicity scorer
When `USE_HF_TOXICITY=False` (the default), toxicity scoring uses a TF-IDF + LogisticRegression classifier trained on a small, hardcoded synthetic dataset. This classifier is deterministic and requires no network access, but its coverage is limited. Enable the HF model for production-grade detection.

### SQLite
The audit store uses SQLite via direct `sqlite3` calls. This is appropriate for single-process development. For production, replace `SQLiteAuditRepository` with a PostgreSQL or other implementation of the `AuditRepository` protocol.

### Semantic topic detection
Semantic similarity checking (via `sentence-transformers`) is only triggered if a policy rule sets `semantic_threshold`. It is not enabled in the default `policy.yaml`. Keyword matching is always active.

### Streaming
The current implementation buffers the full provider response before running output guardrails. Streaming is not supported.

### Policy hot-reload
The policy is loaded once at startup (`@app.on_event("startup")`). Changes to the YAML file require a server restart.
