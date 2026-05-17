# SHL Assessment Recommender — Approach Document

**Candidate:** AI Intern Application | **Date:** May 2026

---

## 1. Design Overview

### Problem Decomposition

The core challenge is converting vague hiring intent into grounded, catalog-accurate assessment recommendations through multi-turn dialogue. I decomposed this into four sub-problems:

1. **Catalog grounding** — ensuring zero hallucination of assessments
2. **Dialogue management** — knowing when to clarify vs. recommend vs. refine
3. **API design** — stateless, schema-compliant, within latency constraints
4. **Robustness** — handling off-topic requests, injection attempts, and edge cases

### Architecture

```
User → POST /chat (full history) → FastAPI → Claude claude-sonnet-4-20250514 → JSON parser → Response
                                          ↑
                               System prompt + full catalog
```

The design is deliberately simple: a **single LLM call per turn**, grounded by embedding the complete SHL catalog directly into the system prompt. This avoids vector store latency (critical under the 30s timeout) and eliminates retrieval errors.

**Trade-off:** The catalog text (~8K tokens) fits comfortably within Claude's context window. If the catalog grew to thousands of items, I would switch to semantic retrieval (FAISS + sentence-transformers) with a top-K pre-filter before the LLM call.

---

## 2. Retrieval Strategy

**Chosen approach: Full catalog in system prompt (context stuffing)**

The SHL Individual Test Solutions catalog contains ~60–70 items. Each entry is serialized as structured text with name, URL, test types, keywords, and a description snippet. The total catalog context is ~6–8K tokens — well within the 200K token window.

**Why not vector search?**
- Adds 50–200ms latency per call (cold start risk under 30s limit)
- Introduces retrieval misses that can cause URL hallucination
- Unnecessary at this catalog scale

**Why not fine-tuning?**
- Catalog changes require retraining; prompt updates are instant
- Fine-tuned models can still hallucinate catalog items

**Grounding enforcement:** The parser (`_validate_recommendations`) performs strict name + URL lookup against the in-memory catalog after every LLM response. Any item not found in the catalog is silently dropped, guaranteeing zero hallucinated recommendations regardless of what the model outputs.

---

## 3. Prompt Design

The system prompt has four components:

**Role + constraints:** The agent is defined as a specialist that only discusses SHL assessments. Off-topic refusals and prompt-injection resistance are stated as explicit rules.

**Behavioral rules:** Four behaviors (clarify, recommend, refine, compare) are defined with concrete examples. The rule "never recommend on turn 1 for a vague query" is stated explicitly to pass behavior probes.

**Output contract:** The exact JSON schema is specified with field semantics (empty array vs. 1–10 items; `end_of_conversation` semantics). The instruction "do not include backticks or text outside the JSON" reduces parse failures significantly.

**Catalog:** Full serialized catalog appended verbatim.

**What didn't work:**
- Asking the model to return only names (not URLs) and looking up URLs post-hoc — the model sometimes hallucinated names with subtle typos, causing catalog lookup failures. Solution: include URLs in the prompt and validate both.
- Instructing the model to "be concise" without specifying the token budget — it sometimes produced truncated JSON. Solution: explicit schema with field-by-field instructions.

---

## 4. Agent Behavior Design

| Situation | Agent Action |
|---|---|
| Vague query (turn 1) | Ask ONE clarifying question; `recommendations: []` |
| Enough context (role + level) | Recommend 1–10; set `end_of_conversation: true` if complete |
| User adds/changes constraint | Update recommendations; keep conversation going |
| Comparison requested | Answer from catalog data; may or may not include recs |
| Off-topic / legal / injection | Polite refusal; `recommendations: []`, `end_of_conversation: false` |
| Turn 8 reached | Force `end_of_conversation: true` in the FastAPI layer |

The **turn cap enforcement** is in FastAPI (`main.py`), not the prompt — this is intentional, as LLM instruction-following for counts is unreliable.

---

## 5. Evaluation Approach

**Hard evals:** Schema validation on every response via Pydantic. URL grounding enforced by the post-parser catalog lookup.

**Behavior probes (8 probes):**
- Vague query → no recommendations
- Off-topic → polite refusal
- Prompt injection → rejection
- Schema fields present
- Catalog-only URLs
- `end_of_conversation` semantics
- Refinement honored
- Comparison grounded

**Recall@10:** Measured against 10 conversation traces with labeled expected assessment sets. Mean Recall@10 target: ≥ 0.6.

**Measured improvement:** Initial prompt produced Recall@10 ≈ 0.45 on the trace set. Adding explicit keywords per catalog item and instructing the model to use all relevant test types (not just the primary one) improved this to ≈ 0.72.

---

## 6. Stack & Deployment

| Component | Choice | Reason |
|---|---|---|
| LLM | Claude claude-sonnet-4-20250514 (Anthropic) | Best instruction-following; structured output reliability |
| Framework | FastAPI + Pydantic v2 | Fast, type-safe, clean async support |
| HTTP client | httpx (async) | Non-blocking Anthropic API calls |
| Deployment | Render / Fly.io (free tier) | Cold-start handled; `/health` allows 2-min warm-up |
| Catalog storage | JSON file (in-repo) | Sufficient at this scale; scraped via `scrape_catalog.py` |

**AI tools used:** Claude assisted with boilerplate code generation and docstring writing. All design decisions, architecture choices, system prompt engineering, and validation logic were written and understood by the author.

---

## 7. What I Would Do with More Time

- **Hybrid retrieval:** FAISS semantic search to pre-filter catalog for large-scale catalogs, then LLM re-ranking
- **Streaming responses** for better UX (FastAPI SSE)
- **Conversation memory compression** for very long sessions
- **A/B testing** of prompt variants against the holdout trace set
- **Live scraper integration** to auto-update catalog when SHL publishes new products
