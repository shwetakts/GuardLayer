# GuardLayer — Cross-Provider Guardrail Policy Engine

GuardLayer is a provider-agnostic LLM governance and guardrail API that sits between an application and an LLM provider.

It allows an organization to define governance policies once in YAML and enforce them consistently across LLM requests and responses.

GuardLayer performs:

- PII detection and redaction
- Toxicity detection
- Denied-topic detection
- Input blocking before the LLM is called
- Output blocking/redaction after the LLM responds
- Policy inheritance and validation
- Structured request tracing
- PII-redacted audit logging
- Provider abstraction
- OpenRouter integration
- Extensible provider adapters

The application is currently deployed as a Docker container on an AWS EC2 instance and is accessible through a public HTTP API.

---

## Table of Contents

1. [Overview](#1-overview)
2. [What GuardLayer Does](#2-what-guardlayer-does)
3. [Architecture](#3-architecture)
4. [Request Flow](#4-request-flow)
5. [Current Deployment](#5-current-deployment)
6. [Using the Deployed API](#6-using-the-deployed-api)
7. [API Endpoints](#7-api-endpoints)
8. [Project Structure](#8-project-structure)
9. [Installation](#9-installation)
10. [Configuration](#10-configuration)
11. [LLM Providers](#11-llm-providers)
12. [OpenRouter Integration](#12-openrouter-integration)
13. [Docker Deployment](#13-docker-deployment)
14. [AWS Deployment](#14-aws-deployment)
15. [Company Integration](#15-company-integration)
16. [Policy Configuration](#16-policy-configuration)
17. [PII Detection](#17-pii-detection)
18. [Toxicity Detection](#18-toxicity-detection)
19. [Topic Detection](#19-topic-detection)
20. [Audit Logging](#20-audit-logging)
21. [Structured Request Context](#21-structured-request-context)
22. [Running Locally](#22-running-locally)
23. [Running the Demo](#23-running-the-demo)
24. [Testing](#24-testing)
25. [Security Considerations](#25-security-considerations)
26. [Current Limitations](#26-current-limitations)
27. [Future Improvements](#27-future-improvements)

---

# 1. Overview

Modern applications often use multiple LLM providers. Each provider may have different APIs, safety mechanisms, models, and configuration.

This creates a governance problem:

```text
Application
   │
   ├── Provider A → custom safety logic
   ├── Provider B → different safety logic
   └── Provider C → different safety logic
```

GuardLayer provides a centralized policy enforcement layer:

```text
Application
      │
      ▼
  GuardLayer
      │
      ├── Policy enforcement
      ├── PII detection
      ├── Toxicity detection
      ├── Topic detection
      ├── Input blocking/redaction
      ├── Output blocking/redaction
      └── Audit logging
      │
      ▼
  LLM Provider
      │
      ▼
     LLM
```

The application calling GuardLayer does not need to implement the governance logic itself.

---

# 2. What GuardLayer Does

GuardLayer follows a "define once, enforce everywhere" model.

## Define once

Governance policies are defined in YAML.

Example policy concepts include:

- PII handling
- Toxicity thresholds
- Denied topics
- Block/redact/allow actions
- Policy inheritance

## Enforce everywhere

The same guardrail engine is applied regardless of which provider is selected.

For example:

```text
Client
  │
  ▼
POST /chat
  │
  ▼
GuardEngine
  │
  ├── Check input
  │
  ├── Block or redact if required
  │
  ▼
ProviderRouter
  │
  ▼
LLM Provider
  │
  ▼
GuardEngine
  │
  ├── Check output
  │
  ├── Block or redact if required
  │
  ▼
Audit Logger
  │
  ▼
Client
```

## Audit uniformly

Every request generates an audit record.

Sensitive information is redacted before being stored.

Raw PII is not intentionally persisted in the audit database.

## Inherit safely

Child policies can extend a parent policy but cannot weaken mandatory governance controls.

For example, a child policy cannot:

- Lower a required toxicity threshold
- Remove mandatory denied topics
- Change a mandatory `block` action into `allow`

---

# 3. Architecture

```text
                         ┌──────────────────────┐
                         │      Client App      │
                         └──────────┬───────────┘
                                    │
                                    │ POST /chat
                                    ▼
                         ┌──────────────────────┐
                         │      FastAPI         │
                         │      /chat           │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    Policy Loader     │
                         │                      │
                         │ YAML policy + hash   │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     GuardEngine      │
                         │                      │
                         │ PII                  │
                         │ Toxicity             │
                         │ Topics               │
                         └──────────┬───────────┘
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                       BLOCK                 ALLOW/
                         │                   REDACT
                         ▼                     │
                    Audit + Return             ▼
                                      ┌──────────────────┐
                                      │ Provider Router  │
                                      └────────┬─────────┘
                                               │
                           ┌───────────────────┼──────────────────┐
                           │                   │                  │
                           ▼                   ▼                  ▼
                     OpenRouter             Ollama          Mock Providers
                           │
                           ▼
                         LLM
                           │
                           ▼
                    Output Guardrails
                           │
                           ▼
                     Audit Logger
                           │
                           ▼
                         Client
```

---

# 4. Request Flow

A request to `/chat` follows these stages.

## Step 1 — Client sends request

Example:

```json
{
  "provider": "openrouter",
  "messages": [
    {
      "role": "user",
      "content": "Hello, can you help me?"
    }
  ]
}
```

## Step 2 — Request context is created

GuardLayer establishes:

- `request_id`
- `session_id`
- `agent_id`

If a request ID is not supplied, GuardLayer generates one.

## Step 3 — Policy is applied

The active YAML policy is loaded and its effective version is represented by a SHA-256 hash.

## Step 4 — Input guardrails run

GuardLayer checks the input for:

- PII
- Toxicity
- Denied topics

Possible actions include:

```text
ALLOW
REDACT
BLOCK
```

If the request is blocked:

```text
Client
  │
  ▼
GuardLayer
  │
  ├── Input violates policy
  │
  ├── Provider is NOT called
  │
  └── Audit record created
```

## Step 5 — Provider is called

If allowed, or after required redaction, GuardLayer sends the request to the selected provider.

The current deployed real provider is OpenRouter.

### LLM Provider API Keys

GuardLayer itself does not require OpenAI or Anthropic API keys to run.

The application is designed around a provider-adapter architecture, so provider credentials are only required when using a real external LLM provider that requires authentication.

For example:

- `provider: "openrouter"` requires a valid `OPENROUTER_API_KEY`.
- A direct OpenAI adapter would require an `OPENAI_API_KEY`.
- A direct Anthropic adapter would require an `ANTHROPIC_API_KEY`.
- `provider: "ollama"` does not require an API key because Ollama runs locally.
- The mock providers (`mock_openai`, `mock_anthropic`, `mock_third`) do not require any API keys.

**Important:** The names `mock_openai` and `mock_anthropic` do not mean that GuardLayer has access to OpenAI or Anthropic accounts. They are deterministic test adapters used to demonstrate that the same guardrail policy can be applied independently of the underlying LLM provider.

When deploying GuardLayer with a real provider, add the appropriate credentials to `.env` or the deployment environment. Never commit API keys to source control.

## Step 6 — Output guardrails run

The LLM response is checked again for:

- PII
- Toxicity
- Denied topics

## Step 7 — Audit record is created

The interaction is recorded after PII redaction.

## Step 8 — Response is returned

The client receives:

- LLM response
- provider
- model
- guardrail status
- final action
- policy version
- audit ID
- request ID
- blocked rules, if applicable

---

# 5. Current Deployment

GuardLayer is currently deployed on AWS using Docker and Amazon EC2.

## Deployment architecture

```text
Internet
   │
   ▼
Public IPv4
   │
   ▼
AWS EC2
   │
   ▼
Docker
   │
   ▼
guardlayer:latest
   │
   ▼
Uvicorn
   │
   ▼
FastAPI
   │
   ├── GuardEngine
   ├── Policy Engine
   ├── Audit Logger
   │
   ▼
OpenRouter
   │
   ▼
LLM
```

## Public API

The current deployed API is available at:

```text
http://3.110.47.189:8000
```

Interactive API documentation:

```text
http://3.110.47.189:8000/docs
```

Health endpoint:

```text
http://3.110.47.189:8000/health
```

OpenAPI specification:

```text
http://3.110.47.189:8000/openapi.json
```

> The public IP and port are deployment-specific. If the EC2 public IP changes, these URLs must be updated. Using an Elastic IP or DNS name is recommended for a more stable production deployment.

---

# 6. Using the Deployed API

GuardLayer is an API service.

A frontend is **not required** to use the application.

Any application capable of making HTTP requests can integrate with GuardLayer.

The simplest interaction is:

```text
Company Application
        │
        │ HTTP POST
        ▼
GuardLayer /chat
        │
        ▼
LLM Provider
        │
        ▼
GuardLayer
        │
        ▼
Company Application
```

---

## 6.1 Health Check

Run:

```bash
curl http://3.110.47.189:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "database": "ok",
  "policy_version": "ea602985d98e793282d6b11f29e8e1c1a7fcb6bf49b78efe9ab34501500e4a46"
}
```

The exact `policy_version` changes whenever the effective policy changes.

---

# 6.2 Send a Chat Request

Example:

```bash
curl -X POST http://3.110.47.189:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openrouter",
    "messages": [
      {
        "role": "user",
        "content": "Hello, can you help me?"
      }
    ]
  }'
```

Example response:

```json
{
  "response": "Of course! What do you need help with?",
  "provider": "openrouter",
  "model": "openai/gpt-3.5-turbo",
  "guardrail_applied": true,
  "final_action": "allow",
  "policy_version": "ea602985d98e793282d6b11f29e8e1c1a7fcb6bf49b78efe9ab34501500e4a46",
  "audit_id": "061bcd43-8d1f-42a7-8b9d-bfe5c4c86ef4",
  "request_id": "249df803-2038-485f-84f1-4f99f63c8b71",
  "blocked_rules": null
}
```

The model is configurable through `OPENROUTER_MODEL`.

---

# 6.3 Supplying Request Context

Applications can provide their own request, session, and agent IDs.

Example:

```bash
curl -X POST http://3.110.47.189:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openrouter",
    "agent_id": "customer-support-agent",
    "session_id": "session-001",
    "request_id": "request-001",
    "messages": [
      {
        "role": "user",
        "content": "How can I reset my password?"
      }
    ]
  }'
```

These identifiers are returned in the response and persisted in the audit record.

---

# 6.4 Interactive Swagger Documentation

GuardLayer exposes automatically generated OpenAPI documentation.

Open:

```text
http://3.110.47.189:8000/docs
```

Swagger provides an interactive interface for testing endpoints such as:

```text
POST /chat
GET  /health
GET  /policy
POST /policy/validate
GET  /audit
```

No custom frontend is required to test the API.

---

# 7. API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/chat` | POST | Send an LLM request through GuardLayer |
| `/health` | GET | Check API, database, and policy health |
| `/docs` | GET | Interactive Swagger/OpenAPI documentation |
| `/openapi.json` | GET | OpenAPI specification |
| `/policy` | GET | Retrieve the active policy |
| `/policy/validate` | POST | Validate a policy |
| `/audit` | GET | Retrieve audit records |

---

## `/chat`

Main LLM gateway endpoint.

Request:

```json
{
  "provider": "openrouter",
  "messages": [
    {
      "role": "user",
      "content": "Hello"
    }
  ],
  "agent_id": "optional-agent-id",
  "session_id": "optional-session-id",
  "request_id": "optional-request-id"
}
```

Response:

```json
{
  "response": "Hello!",
  "provider": "openrouter",
  "model": "openai/gpt-3.5-turbo",
  "guardrail_applied": true,
  "final_action": "allow",
  "policy_version": "...",
  "audit_id": "...",
  "request_id": "...",
  "blocked_rules": null
}
```

---

## `/health`

Example:

```bash
curl http://3.110.47.189:8000/health
```

Returns:

```json
{
  "status": "ok",
  "database": "ok",
  "policy_version": "..."
}
```

---

## `/policy`

Returns the active policy.

```bash
curl http://3.110.47.189:8000/policy
```

---

## `/policy/validate`

Validates a policy without necessarily replacing the active policy.

Example:

```bash
curl -X POST http://3.110.47.189:8000/policy/validate \
  -H "Content-Type: application/json" \
  -d '{
    "rules": []
  }'
```

---

## `/audit`

Returns audit records.

Example:

```bash
curl "http://3.110.47.189:8000/audit"
```

Filtering is supported by:

- provider
- agent ID
- session ID

Example:

```bash
curl "http://3.110.47.189:8000/audit?provider=openrouter"
```

---

# 8. Project Structure

```text
GuardLayer/
│
├── app/
│   ├── config.py
│   ├── dependencies.py
│   └── main.py
│
├── core/
│   ├── checks/
│   │   ├── pii_detector.py
│   │   ├── topic_denier.py
│   │   └── toxicity_scorer.py
│   │
│   ├── exceptions.py
│   ├── guard_engine.py
│   ├── logging_context.py
│   ├── models.py
│   └── policy_loader.py
│
├── providers/
│   ├── base.py
│   ├── mock_openai.py
│   ├── mock_anthropic.py
│   ├── mock_third.py
│   ├── openrouter.py
│   ├── ollama.py
│   └── router.py
│
├── storage/
│   ├── base.py
│   ├── sqlite_repository.py
│   └── audit_logger.py
│
├── policy/
│   ├── base_policy.yaml
│   └── policy.yaml
│
├── tests/
│
├── data/
│   └── audit.db
│
├── demo.py
├── Dockerfile
├── requirements.txt
├── .env
└── README.md
```

> The exact file list may vary depending on enabled providers and implementation changes.

---

# 9. Installation

## Requirements

For local development:

- Python 3.11+
- pip
- Git
- Optional: Docker

For the AWS deployment:

- AWS EC2
- Docker
- Internet connectivity from the EC2 instance
- OpenRouter API credentials

---

## Python Installation

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\activate
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Current core dependencies:

| Package | Purpose |
|---|---|
| `fastapi` | Web API framework |
| `uvicorn` | ASGI application server |
| `pydantic` | Request/response models |
| `pydantic-settings` | Environment configuration |
| `pyyaml` | YAML policy parsing |
| `scikit-learn` | Toxicity fallback classifier |
| `httpx` | Async HTTP requests |
| `sqlalchemy` | Database abstraction/support |
| `psycopg[binary]` | PostgreSQL driver |
| `psycopg2-binary` | PostgreSQL compatibility |
| `openai` | OpenAI-compatible LLM API client, including OpenRouter |
| `pytest` | Testing |

---

# 10. Configuration

GuardLayer reads configuration from environment variables and/or a `.env` file.

## Example `.env`

```text
OPENROUTER_API_KEY=your-openrouter-api-key
OPENROUTER_MODEL=openai/gpt-3.5-turbo

GUARDLAYER_LOG_LEVEL=INFO
GUARDLAYER_PROVIDER_TIMEOUT=60
```

Never commit `.env` to Git.

Add it to `.gitignore`:

```text
.env
```

---

## Configuration Variables

| Variable | Description |
|---|---|
| `OPENROUTER_API_KEY` | API key used to authenticate with OpenRouter |
| `OPENROUTER_MODEL` | Model used by the OpenRouter provider |
| `GUARDLAYER_POLICY_PATH` | Path to active YAML policy |
| `GUARDLAYER_DB_PATH` | Path to audit database |
| `GUARDLAYER_DATABASE_URL` | Database connection URL |
| `GUARDLAYER_LOG_LEVEL` | Logging level |
| `GUARDLAYER_PROVIDER_TIMEOUT` | Provider timeout in seconds |
| `GUARDLAYER_OLLAMA_BASE_URL` | Ollama endpoint |
| `GUARDLAYER_OLLAMA_MODEL` | Ollama model |
| `GUARDLAYER_EMBEDDING_MODEL_NAME` | Optional embedding model |
| `USE_HF_TOXICITY` | Enables Hugging Face toxicity model |
| `GUARDLAYER_TOXICITY_MODEL_NAME` | Hugging Face toxicity model |
| `USE_HF_PII_NER` | Enables Hugging Face NER |
| `GUARDLAYER_PII_NER_MODEL_NAME` | Hugging Face NER model |

The exact defaults are defined by `app/config.py`.

---

# 11. LLM Providers

GuardLayer uses a provider abstraction so that guardrail logic is independent of the underlying LLM provider.

The router selects an adapter based on the `provider` field.

Currently supported provider types include:

```text
openrouter
ollama
mock_openai
mock_anthropic
mock_third
```

---

## OpenRouter

OpenRouter is the current real provider used by the deployed application.

GuardLayer communicates with OpenRouter using the OpenAI-compatible API interface and the `openai` Python package.

This means:

```text
GuardLayer
    │
    │ OpenAI-compatible API
    ▼
OpenRouter
    │
    ▼
Selected LLM
```

The client application does not need to know the OpenRouter API key.

The key remains on the GuardLayer server.

---

## Ollama

Ollama can be used for local inference.

Example configuration:

```text
GUARDLAYER_OLLAMA_BASE_URL=http://localhost:11434
GUARDLAYER_OLLAMA_MODEL=llama2
```

Ollama is optional and is not required for the current AWS OpenRouter deployment.

---

## Mock Providers

Mock providers are deterministic providers used for:

- Tests
- Demonstrations
- Guardrail validation
- Provider abstraction testing

They do not require an external LLM API.

---

# 12. OpenRouter Integration

OpenRouter is currently the primary real LLM integration for the deployed GuardLayer instance.

## Required configuration

```text
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-3.5-turbo
```

The model can be changed without modifying the GuardLayer request interface.

For example, the client continues to send:

```json
{
  "provider": "openrouter",
  "messages": [
    {
      "role": "user",
      "content": "Hello"
    }
  ]
}
```

The selected model is controlled server-side through configuration.

---

## Why is the `openai` package required?

OpenRouter exposes an OpenAI-compatible API.

Therefore GuardLayer uses the `openai` Python SDK as the client library.

This does **not** mean the request is necessarily sent to the OpenAI API.

For the deployed configuration:

```text
GuardLayer
    │
    │ openai Python SDK
    ▼
OpenRouter API
    │
    ▼
Configured OpenRouter model
```

---

# 13. Docker Deployment

GuardLayer is packaged as a Docker image.

## Build

From the project root:

```bash
docker build -t guardlayer:latest .
```

Check the image:

```bash
docker images | grep guardlayer
```

---

## Run

The application runs Uvicorn inside the container on port `8080`.

Expose it as port `8000` on the host:

```bash
docker run -d \
  --name guardlayer \
  -p 8000:8080 \
  --env-file .env \
  guardlayer:latest
```

Check:

```bash
docker ps
```

Expected mapping:

```text
0.0.0.0:8000->8080/tcp
```

---

## Verify the container

```bash
curl http://localhost:8000/health
```

Expected:

```json
{
  "status": "ok",
  "database": "ok",
  "policy_version": "..."
}
```

Check logs:

```bash
docker logs guardlayer
```

---

# 14. AWS Deployment

The current GuardLayer deployment uses Amazon EC2 as the compute environment.

## Current AWS architecture

```text
                    Internet
                       │
                       ▼
              Public IPv4 Address
                3.110.47.189
                       │
                       ▼
              ┌─────────────────┐
              │    AWS EC2      │
              │                 │
              │ Ubuntu Linux    │
              │                 │
              │ Docker         │
              │   │             │
              │   ▼             │
              │ GuardLayer      │
              │ FastAPI         │
              │ Uvicorn         │
              └────────┬────────┘
                       │
                       │ HTTPS/API request
                       ▼
                  OpenRouter
                       │
                       ▼
                      LLM
```

---

## AWS services currently involved

### Amazon EC2

EC2 provides the virtual server running GuardLayer.

The application is running inside a Docker container on the EC2 instance.

### Elastic IP / Public IPv4

The deployment uses a public IPv4 address for external access.

Current endpoint:

```text
3.110.47.189
```

A stable Elastic IP or DNS name should be used for a production deployment.

### EC2 Security Group

The EC2 security group controls inbound traffic.

Port `8000` must be reachable for the current HTTP API deployment.

Recommended production configuration is to avoid exposing the application directly to the public internet and instead place it behind a reverse proxy/load balancer with HTTPS.

---

## AWS services not required by the current deployment

The current GuardLayer deployment does not require:

- AWS Lambda
- Amazon ECS
- Amazon EKS
- Amazon RDS
- API Gateway
- CloudFront
- Route 53

These can be introduced later depending on production requirements.

If an AWS load balancer is configured separately, it should only be described as part of the GuardLayer architecture if it is actually routing traffic to the GuardLayer EC2 instance.

---

# 15. Company Integration

GuardLayer is designed to be used as a centralized LLM gateway.

A company can integrate it without installing a frontend.

Instead of:

```text
Company Application
        │
        ▼
LLM Provider
```

the application can use:

```text
Company Application
        │
        ▼
GuardLayer
        │
        ├── Input guardrails
        ├── Policy enforcement
        ├── PII detection
        ├── Toxicity detection
        ├── Topic detection
        │
        ▼
LLM Provider
        │
        ▼
GuardLayer
        │
        ├── Output guardrails
        ├── PII redaction
        └── Audit logging
        │
        ▼
Company Application
```

The company application only needs to call the GuardLayer API.

---

## Example company integration

The company sends:

```http
POST /chat
Content-Type: application/json
```

with:

```json
{
  "provider": "openrouter",
  "agent_id": "support-agent",
  "session_id": "session-123",
  "messages": [
    {
      "role": "user",
      "content": "How can I reset my password?"
    }
  ]
}
```

GuardLayer then:

1. Checks the input against policy.
2. Blocks or redacts unsafe content if required.
3. Calls the configured LLM provider.
4. Checks the LLM response.
5. Redacts unsafe output if required.
6. Creates an audit record.
7. Returns the final response.

The company does **not** need to expose its LLM provider credentials to its frontend or end users.

---

# 16. Policy Configuration

Policies are defined using YAML.

The project contains:

```text
policy/
├── base_policy.yaml
└── policy.yaml
```

`base_policy.yaml` defines mandatory governance controls.

`policy.yaml` can extend the base policy.

The policy loader:

1. Loads the YAML policy.
2. Resolves inheritance.
3. Validates policy safety.
4. Produces the effective policy.
5. Generates a SHA-256 policy version hash.

The policy version is returned by:

```text
GET /health
```

and included in `/chat` responses and audit records.

---

## Policy inheritance

A child policy cannot weaken mandatory parent controls.

Examples of prohibited weakening:

```text
Parent toxicity threshold: 0.70
Child toxicity threshold: 0.90
```

or:

```text
Parent denied topic: credential theft
Child: removes credential theft
```

or:

```text
Parent action: block
Child action: allow
```

These changes are rejected by the policy loader.

---

# 17. PII Detection

GuardLayer detects PII before sending content to an LLM and again when inspecting the LLM response.

## Regex-based detection

The baseline detector supports:

- Email addresses
- Phone numbers
- Credit-card-like number sequences
- Luhn validation for credit cards

Example:

```text
My email is alice@example.com
```

can be transformed before storage or forwarding according to policy.

---

## Hugging Face NER

Optional NER-based PII detection can detect entities such as:

- PERSON
- ORGANIZATION
- LOCATION

Enable with:

```text
USE_HF_PII_NER=True
```

The NER functionality is optional and should only be enabled when the required ML dependencies are installed.

---

# 18. Toxicity Detection

GuardLayer supports toxicity checking.

When the Hugging Face toxicity model is disabled, GuardLayer can use a lightweight TF-IDF + LogisticRegression fallback.

This fallback:

- Requires no model download
- Works locally
- Is deterministic
- Is suitable for demonstration/testing
- Has limited coverage compared with a production-grade classifier

The optional Hugging Face classifier can be enabled through configuration.

```text
USE_HF_TOXICITY=True
```

---

# 19. Topic Detection

GuardLayer supports denied-topic detection.

The basic mechanism uses keyword matching.

For policies configured to use semantic similarity, an embedding model can be used.

Topic rules can therefore be used to prevent requests involving prohibited subjects from reaching the provider.

Example:

```text
User
  │
  ▼
"How can I steal someone's credentials?"
  │
  ▼
TopicDenier
  │
  ▼
BLOCK
  │
  ├── Provider not called
  └── Audit record created
```

---

# 20. Audit Logging

Every request generates an audit record.

The audit system uses an abstraction:

```text
AuditRepository
```

with the current implementation backed by SQLite.

This allows the storage implementation to be replaced in the future without changing the guardrail engine.

---

## Audit fields

Typical audit fields include:

| Field | Description |
|---|---|
| `audit_id` | UUID identifying the audit event |
| `timestamp` | UTC timestamp |
| `provider` | Provider used |
| `request_id` | Request identifier |
| `session_id` | Session identifier |
| `agent_id` | Agent identifier |
| `policy_version` | Effective policy SHA-256 hash |
| `input_check_result` | Input guardrail result |
| `output_check_result` | Output guardrail result |
| `final_action` | `allow`, `redact`, or `block` |
| `latency_ms` | Total request latency |
| `called_provider` | Whether provider was reached |
| `input_text` | PII-redacted input |
| `output_text` | PII-redacted output |

---

## PII-safe audit storage

Before writing to the database:

```text
Input
  │
  ▼
PII Detector
  │
  ▼
Redacted Input
  │
  ▼
Audit Database
```

The same process is applied to provider output.

The intention is that raw PII is not persisted in audit records.

---

# 21. Structured Request Context

GuardLayer uses Python `contextvars` to maintain request-specific context.

The following identifiers are tracked:

```text
request_id
session_id
agent_id
```

These values are automatically included in structured application logs.

Example:

```json
{
  "timestamp": "2026-08-13T07:54:50.874353Z",
  "level": "INFO",
  "logger": "app.main",
  "message": "Policy loaded.",
  "request_id": "N/A",
  "session_id": "N/A",
  "agent_id": "N/A"
}
```

During an actual request, the identifiers are populated.

This provides traceability across:

```text
Client request
      │
      ▼
GuardLayer
      │
      ├── Guardrail checks
      ├── Provider call
      ├── Logging
      └── Audit
```

---

# 22. Running Locally

## Create virtual environment

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## Install dependencies

```bash
pip install -r requirements.txt
```

---

## Configure environment

Create `.env`:

```text
OPENROUTER_API_KEY=your-key
OPENROUTER_MODEL=openai/gpt-3.5-turbo
```

Do not commit this file.

---

## Start FastAPI

```bash
uvicorn app.main:app --reload
```

The application normally runs on:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

Health:

```text
http://127.0.0.1:8000/health
```

---

## Local `/chat` request

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openrouter",
    "messages": [
      {
        "role": "user",
        "content": "Hello, can you help me?"
      }
    ]
  }'
```

---

# 23. Running the Demo

The project contains:

```text
demo.py
```

Run:

```bash
python demo.py
```

The demo is designed to demonstrate the guardrail engine and provider abstraction without requiring a production LLM call.

The demo covers:

- PII redaction
- Toxic input blocking
- Audit logging
- Provider abstraction
- Third-provider extensibility
- Denied-topic blocking
- Policy inheritance validation
- NER-based PII detection
- Request/session/agent context

---

# 24. Testing

Run the full test suite:

```bash
python -m pytest tests -v
```

Specific test files can be executed with:

```bash
python -m pytest tests/test_phase1.py -v
python -m pytest tests/test_phase2.py -v
python -m pytest tests/test_phase3.py -v
python -m pytest tests/test_phase4.py -v
python -m pytest tests/test_phase5.py -v
python -m pytest tests/test_phase6.py -v
python -m pytest tests/test_phase7.py -v
```

Integration tests:

```bash
python -m pytest tests/test_integration.py -v
```

Component tests:

```bash
python -m pytest \
  tests/test_guard_engine.py \
  tests/test_pii.py \
  tests/test_policy.py \
  -v
```

The test suite is designed to avoid unnecessary external model downloads.

---

# 25. Security Considerations

## API keys

LLM provider credentials must remain server-side.

Do not place:

```text
OPENROUTER_API_KEY
```

in:

- Frontend JavaScript
- Browser requests
- Git repositories
- Public README files
- Docker images

The client should call:

```text
Client → GuardLayer
```

rather than:

```text
Client → OpenRouter
```

with the provider key exposed to the client.

---

## `.env`

Never commit:

```text
.env
```

to source control.

Recommended `.gitignore`:

```text
.env
.venv/
__pycache__/
*.pyc
data/*.db
```

---

## Public API

The current deployment uses plain HTTP:

```text
http://3.110.47.189:8000
```

This is suitable for development/demo access but is **not the recommended production configuration**.

For production, GuardLayer should be placed behind:

```text
Internet
    │
    ▼
HTTPS / TLS
    │
    ▼
Load Balancer / Reverse Proxy
    │
    ▼
GuardLayer
```

The production deployment should also consider:

- HTTPS/TLS
- Authentication
- Authorization
- Rate limiting
- Request size limits
- Network restrictions
- Secret management
- Centralized logging
- Monitoring
- Database backups
- High availability

---

# 26. Current Limitations

## No custom frontend

GuardLayer currently exposes an API and Swagger UI rather than a custom web frontend.

This is intentional because the core product is the LLM governance API.

A frontend can be added later for:

- Chat
- Policy management
- Audit visualization
- Monitoring
- Guardrail statistics

---

## HTTP rather than HTTPS

The current public demo endpoint uses HTTP.

Production deployments should use HTTPS.

---

## Authentication

The current API does not provide a full enterprise authentication/authorization layer.

Authentication should be added before exposing the service to untrusted users.

---

## SQLite

The current deployment uses SQLite for audit persistence.

SQLite is appropriate for a small/single-instance deployment but is not ideal for a high-scale multi-instance production architecture.

A future deployment can use:

```text
GuardLayer
    │
    ▼
PostgreSQL
```

for centralized audit storage.

Amazon RDS PostgreSQL is one possible production option.

---

## Streaming

The current implementation buffers the complete provider response before output guardrails are applied.

Streaming responses are not currently supported.

---

## Policy hot reload

The policy is loaded during application startup.

Changing the YAML file requires restarting the application unless a hot-reload mechanism is added.

---

## Toxicity fallback model

The lightweight TF-IDF + LogisticRegression toxicity fallback is useful for demonstration and development but should not be considered equivalent to a production-grade safety classifier.

---

# 27. Future Improvements

Potential production enhancements include:

### Security

- HTTPS/TLS
- API authentication
- OAuth/JWT
- Role-based access control
- API key management
- AWS Secrets Manager

### AWS infrastructure

```text
Route 53
    │
    ▼
Application Load Balancer
    │
    ▼
GuardLayer
    │
    ▼
EC2 / ECS
```

### Database

Replace SQLite with PostgreSQL/RDS for:

- Multi-instance deployments
- Concurrent access
- Backup
- High availability
- Centralized audit records

### Observability

Add:

- CloudWatch metrics
- CloudWatch logs
- Request latency dashboards
- Guardrail violation metrics
- Provider failure metrics
- Alerting

### Frontend

A lightweight administrative frontend could provide:

```text
┌───────────────────────────────────┐
│          GuardLayer UI            │
├───────────────────────────────────┤
│                                   │
│  Health       ● Healthy           │
│                                   │
│  Requests     12,481              │
│  Blocked      1,284               │
│  Redacted     2,431               │
│                                   │
│  Policy Version                   │
│  ea602985...                      │
│                                   │
│  Recent Audit Events              │
│  ─────────────────────────────    │
│  Request       Action     Provider│
│  req-001       allow      OpenRouter
│  req-002       block      OpenRouter
│  req-003       redact     OpenRouter
│                                   │
└───────────────────────────────────┘
```

This would provide operational visibility without changing the underlying GuardLayer API.

---

# Summary

GuardLayer provides a centralized policy enforcement layer for LLM applications.

The current deployment demonstrates the complete flow:

```text
                 Company Application
                         │
                         ▼
                ┌─────────────────┐
                │    GuardLayer   │
                │                 │
                │ Policy Engine   │
                │ PII Detection   │
                │ Toxicity        │
                │ Topic Rules     │
                │ Audit Logging   │
                └────────┬────────┘
                         │
                         ▼
                    OpenRouter
                         │
                         ▼
                        LLM
                         │
                         ▼
                Output Guardrails
                         │
                         ▼
                    Audit Log
                         │
                         ▼
                Company Application
```

The current deployed API can be tested through:

```text
http://3.110.47.189:8000/docs
```

The core integration point is:

```text
POST /chat
```

A client only needs to send a standard JSON request to GuardLayer. GuardLayer handles policy enforcement, provider communication, output validation, and audit logging behind the API boundary.
