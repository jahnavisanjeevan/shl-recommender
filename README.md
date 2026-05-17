# SHL Assessment Recommender

A conversational FastAPI agent that helps hiring managers find the right SHL Individual Test Solution assessments through natural dialogue.

## Files

```
shl-recommender/
├── main.py                  # FastAPI app (POST /chat, GET /health)
├── scrape_catalog.py        # One-time catalog scraper (run before starting)
├── evaluate.py              # Evaluation harness (behavior probes + recall)
├── requirements.txt         # Python dependencies
├── render.yaml              # Render deployment config
├── fly.toml                 # Fly.io deployment config
├── Dockerfile               # Docker build
├── approach_document.md     # 2-page design write-up
└── catalog/
    └── shl_catalog.json     # Pre-scraped catalog (ready to use)
```

## Quick Start (Local)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 3. (Optional) Re-scrape the catalog

The catalog is pre-included. To refresh it from the SHL website:

```bash
python scrape_catalog.py           # full scrape with product details
python scrape_catalog.py --no-detail   # faster, no detail page visits
```

### 4. Start the server

```bash
uvicorn main:app --reload --port 8000
```

### 5. Test it

```bash
# Health check
curl http://localhost:8000/health

# Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "I am hiring a Java developer who works with stakeholders"}
    ]
  }'
```

### 6. Run evaluation

```bash
pip install requests   # if not already installed
python evaluate.py --base-url http://localhost:8000
```

---

## Deployment

### Option A: Render (recommended — free tier)

1. Push this folder to a GitHub repo
2. Go to [render.com](https://render.com) → New Web Service → connect your repo
3. It auto-detects `render.yaml`
4. Add environment variable: `ANTHROPIC_API_KEY = sk-ant-...`
5. Deploy — your URL will be `https://shl-recommender.onrender.com`

**Note:** Render free tier has cold starts. The evaluator allows 2 minutes for `/health` to respond.

### Option B: Fly.io

```bash
# Install flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth login
fly launch --no-deploy
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly deploy
```

### Option C: Railway

1. New project → Deploy from GitHub
2. Set `ANTHROPIC_API_KEY` in Variables
3. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Option D: Docker

```bash
docker build -t shl-recommender .
docker run -e ANTHROPIC_API_KEY=sk-ant-... -p 8000:8000 shl-recommender
```

---

## API Reference

### GET /health
```json
{"status": "ok"}
```

### POST /chat

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "Hiring a Java developer"},
    {"role": "assistant", "content": "...previous agent reply..."},
    {"role": "user", "content": "Mid-level, 4 years experience"}
  ]
}
```

**Response:**
```json
{
  "reply": "Here are 5 assessments for a mid-level Java developer...",
  "recommendations": [
    {"name": "Java 8 (New)", "url": "https://www.shl.com/...", "test_type": "K"},
    {"name": "OPQ32r", "url": "https://www.shl.com/...", "test_type": "P"}
  ],
  "end_of_conversation": false
}
```

**Schema rules:**
- `recommendations` is `[]` when clarifying or refusing
- `recommendations` has 1–10 items when committed to a shortlist
- `end_of_conversation: true` only when the task is complete and recommendations are present
- Max 8 turns per conversation (enforced server-side)

---

## Scoring Criteria

| Criterion | What's tested |
|---|---|
| Hard evals | Schema compliance, catalog-only URLs, 8-turn cap |
| Recall@10 | Fraction of relevant assessments in top-10 recommendations |
| Behavior probes | Vague query refusal, off-topic refusal, refinement, comparison grounding |
