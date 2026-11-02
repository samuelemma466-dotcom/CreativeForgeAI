# Free provider policy

Last checked: 2026-11-02 (Stage 1 local acceptance complete)

## Rules

- CreativeForge remains usable without any cloud account, key, payment method, or hosted AI service.
- `FREE_ONLY` is enforced in the backend and cannot be disabled by an API request.
- No paid model, billing flow, paid fallback, credit purchase, or card-required trial may be introduced.
- Local model detection must not download models. Never make a model pull part of setup or connection
  testing.
- A provider described as free must have its **API** terms, model eligibility, quota, card requirement,
  commercial-use terms, and automation support checked against current official sources.
- A provider is not operationally verified until a real request succeeds with a credential configured
  by the owner. Do not infer API access from a free website or an account signup page.
- When a free quota is exhausted, stop or use another provider whose free path is independently
  verified. Never try a paid model.

## Current state

| Path | Cost category | Current configuration | Verification state |
| --- | --- | --- | --- |
| Ollama | Local software and local inference; no hosted API charge | Selected by default at `http://127.0.0.1:11434` | **Verified 2026-11-02:** server and installed models detected; real chat returned `UI_OK` from `llama3.2:3b` through the UI. The connection check does not load a model. Remote Ollama URLs are rejected with HTTP 422 before any request. |
| OpenRouter adapter | Online; only model IDs ending `:free` are accepted by the existing adapter | No key configured | Not tested with credentials; no current pricing/quota/commercial terms verified for this project. |
| Gemini adapter | Online; existing code restricts its model ID pattern | No key configured | Not tested with credentials; no current free API quota/card/commercial terms verified for this project. |
| Groq adapter | Online; existing code restricts its model ID allowlist | No key configured | Not tested with credentials; no current free plan/card/commercial terms verified for this project. |

Stage 1 acceptance is complete for the local Ollama path. Cloud adapter code exists in the repository,
but the application must not claim cloud failover or current free eligibility as verified. The assistant
defaults to local Ollama; local selection builds an Ollama-only chain and a local failure does not
silently send the prompt to a cloud provider.

## Hardware and installed local models

The audited laptop has 7.6 GiB RAM, an Intel i5-2540M (2 physical cores / 4 threads), and legacy
integrated graphics. The audit found `llama3.2:3b` (about 2.0 GB) and `qwen2.5:1.5b` (about 986 MB)
installed. These inventory results can change; query Ollama at runtime. Do not download a larger model
for this project. Swap is not physical RAM.

## Future cloud verification record

Before enabling a cloud path, add a dated record here with direct official documentation/pricing links
and the checked model IDs, API rates and quotas, card requirements, commercial-use restrictions, and
whether automation is supported. Then test a real request using an owner-configured credential and
document the result without exposing the secret. If the terms or quota cannot be established, leave
the path disabled. No cloud provider has been verified or tested in this handoff.
