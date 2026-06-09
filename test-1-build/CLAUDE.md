# CLAUDE.md — Lead Scoring Agent
## Northern Coast Beverages — Technical Test #1

This is the **complete build specification** for a deployed lead-scoring HTTP endpoint.
Claude Code should read this file in full before writing any code.

---

## Project Context

**Role applying for:** Senior AI Platform Engineer, Northern Coast Beverages.  
**Goal:** A publicly-deployed Vercel endpoint that accepts a B2B beverage lead transcript and returns a scored routing decision.  
**Evaluation criteria (in order of weight):** does it ship → code quality & defensible architecture → README reasoning → failure handling.  
**Time budget:** ~2 hours. Do not over-engineer. Ship clean, working code.

---

## Non-Negotiable Architecture Decision

Use a **hybrid approach — extraction then deterministic scoring:**

1. LLM (`claude-haiku-4-5-20251001`) does **signal extraction only** — parses the conversation into structured fields.
2. A **pure Python deterministic function** converts those fields into a final score, tier, and routing.

**Do NOT** ask the LLM to output a score directly. That is non-reproducible, non-defensible, and breaks under adversarial inputs.

**Fallback path (mandatory):** if the LLM call fails, times out, or returns unparseable output, a keyword-based fallback scorer must run and still return valid scored JSON. The endpoint must **never** return a 5xx to the evaluator.

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Runtime | Python 3.11 | Dev preference, matches Vercel Python support |
| Serving | Vercel Python serverless (`api/`) | Requirement |
| LLM | `claude-haiku-4-5-20251001` | Fast (<5s), cheap, sufficient for extraction from short transcripts |
| Validation | Pydantic v2 | Type safety on I/O contracts |
| No framework | Raw HTTP handler | Minimal deps, faster cold start |

---

## Project File Structure

Create exactly this layout:

```
.
├── api/
│   └── score.py              # Vercel entry point — handles POST /api/score
├── lib/
│   ├── __init__.py           # Empty
│   ├── models.py             # Pydantic models for I/O and extracted signals
│   ├── extractor.py          # LLM extraction logic
│   ├── scorer.py             # Deterministic scoring function
│   └── fallback.py           # Keyword-based fallback scorer (no LLM dependency)
├── tests/
│   └── test_scorer.py        # Unit tests for the deterministic scorer
├── vercel.json
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Input / Output Contracts

### POST /api/score — Request body
```json
{
  "lead_id": "L001",
  "channel": "whatsapp",
  "conversation": [
    {"role": "lead", "text": "Hi, looking for wholesale Monster Energy supply for Singapore. 1 FCL/month."},
    {"role": "agent", "text": "Could you confirm your import license and history?"},
    {"role": "lead", "text": "Yes, licensed 4 years. Currently import 2 brands."}
  ]
}
```

### Response body
```json
{
  "lead_id": "L001",
  "score": 78,
  "tier": "Warm",
  "routing": "kam_handoff",
  "reasoning": "Licensed importer, moderate volume single-brand focus — eligible for KAM follow-up."
}
```

**Field rules:**
- `score`: integer 0–100
- `tier`: exactly one of `"Hot"` | `"Warm"` | `"Cold"`
- `routing`: exactly one of `"kam_handoff"` | `"nurture_pool"` | `"auto_archive"`
- Tier → Routing mapping is 1:1 (Hot → kam_handoff, Warm → nurture_pool, Cold → auto_archive)
- `reasoning`: 1–2 sentence human-readable string, generated from a template (NOT from the LLM)

---

## `lib/models.py` — Pydantic Models

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: str
    text: str


class LeadInput(BaseModel):
    lead_id: str
    channel: str = "unknown"
    conversation: list[ConversationTurn] = Field(default_factory=list)


class ExtractedSignals(BaseModel):
    """Structured output of the LLM extraction step."""
    volume_fcl_per_month: float | None    # None if not mentioned
    license_status: Literal["valid", "in_process", "none", "unclear"]
    product_fit: bool                      # True if a portfolio brand is named
    years_importing: int | None           # None if not mentioned
    retail_accounts: int | None           # None if not mentioned
    existing_brands: int | None           # Count of brands they currently import
    is_consumer: bool                     # True if clearly a retail/personal request
    raw_channel: str                      # Pass-through from input


class ScoredOutput(BaseModel):
    lead_id: str
    score: int
    tier: Literal["Hot", "Warm", "Cold"]
    routing: Literal["kam_handoff", "nurture_pool", "auto_archive"]
    reasoning: str
```

---

## `lib/scorer.py` — Deterministic Scoring

Implement `compute_score(signals: ExtractedSignals, lead_id: str) -> ScoredOutput`.

### Scoring Rubric (implement exactly)

| Dimension | Max | Rules |
|---|---|---|
| **License** | 30 | `valid` = 30 · `in_process` = 13 · `none` = 0 · `unclear` = 5 |
| **Volume** | 30 | ≥3 FCL = 30 · 1–2.99 = 18 · 0.5–0.99 = 8 · >0 but <0.5 = 3 · `None`/unclear = 5 · consumer = 0 |
| **Product fit** | 20 | portfolio brand named = 20 · no named brand = 10 |
| **Business signals** | 20 | 2 pts/year importing (max 10) + 2 pts per 50 retail accounts (max 6) + 2 pts per existing brand (max 4) |

```
total_score = license_pts + volume_pts + product_fit_pts + business_pts
```

**Consumer override:** if `is_consumer = True`, immediately return `score=0, tier="Cold", routing="auto_archive"` — skip all other scoring.

**Portfolio brands (product_fit = True if any of these appear in transcript):**
`Coca-Cola`, `Coke`, `Monster Energy`, `Monster`, `Red Bull`, `Fanta`, `Sprite`, `Powerade`

### Tier Thresholds

```python
if score >= 70:
    tier = "Hot"
    routing = "kam_handoff"
elif score >= 35:
    tier = "Warm"
    routing = "nurture_pool"
else:
    tier = "Cold"
    routing = "auto_archive"
```

### Reasoning Templates

Generate `reasoning` from these string templates — do NOT call the LLM for this:

```python
def build_reasoning(signals: ExtractedSignals, score: int, tier: str) -> str:
    if signals.is_consumer:
        return "Consumer or personal-use request detected — not a wholesale lead."

    vol = f"{signals.volume_fcl_per_month:.0f} FCL/month" if signals.volume_fcl_per_month else "volume unspecified"
    lic = {
        "valid": "licensed importer",
        "in_process": "license pending",
        "none": "no import license",
        "unclear": "license status unclear",
    }[signals.license_status]

    if tier == "Hot":
        return f"Strong B2B signals: {lic}, {vol}. Ready for KAM engagement."
    elif tier == "Warm":
        if signals.license_status == "in_process":
            return f"License in process — nurture until confirmed. {vol} indicates real wholesale intent."
        return f"{lic.capitalize()}, {vol} — solid prospect, not yet KAM-ready. Add to nurture pool."
    else:
        parts = []
        if signals.license_status in ("none", "unclear"):
            parts.append("no verified import license")
        if not signals.volume_fcl_per_month or signals.volume_fcl_per_month < 0.5:
            parts.append("insufficient volume signals")
        reason = " and ".join(parts) if parts else "insufficient qualifying signals"
        return f"Lead does not meet threshold: {reason}. Auto-archived."
```

---

## `lib/extractor.py` — LLM Signal Extraction

### System Prompt (use verbatim)

```python
SYSTEM_PROMPT = """You are a signal extractor for a B2B beverage distributor.
Given a conversation transcript, extract structured data and return ONLY valid JSON.
No preamble. No markdown fences. No explanation.

Portfolio brands: Coca-Cola, Coke, Monster Energy, Monster, Red Bull, Fanta, Sprite, Powerade.

Return exactly this JSON schema:
{
  "volume_fcl_per_month": <float or null>,
  "license_status": "valid" | "in_process" | "none" | "unclear",
  "product_fit": <true or false>,
  "years_importing": <int or null>,
  "retail_accounts": <int or null>,
  "existing_brands": <int or null>,
  "is_consumer": <true or false>
}

Extraction rules:
- volume_fcl_per_month: normalize to monthly FCL. "3 FCL/month" → 3.0. "2-3 FCL" → 2.5. "a few cans" → null (is_consumer=true).
- license_status: "valid" if they confirm having a license. "in_process" if pending/expected. "none" if explicitly absent. "unclear" if never mentioned.
- product_fit: true only if a portfolio brand is explicitly named or clearly implied (e.g. "original Austrian product" for Red Bull context).
- is_consumer: true if this is clearly personal, retail, or small-office use — not a wholesale distributor inquiry.
- years_importing: integer if stated ("8 years importing" → 8), else null.
- retail_accounts: integer if stated ("250 retail accounts" → 250), else null.
- existing_brands: count of distinct brands they currently import if mentioned, else null."""
```

### Extractor Function

```python
import json
import os
import anthropic
from lib.models import ExtractedSignals, LeadInput

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-haiku-4-5-20251001"
TIMEOUT_SECONDS = 18  # leave room for fallback within the 30s Vercel budget


def extract_signals(lead: LeadInput) -> ExtractedSignals | None:
    """
    Call Claude Haiku to extract structured signals from the conversation.
    Returns None on any failure — caller must invoke fallback_score().
    """
    transcript = "\n".join(
        f"[{turn.role.upper()}]: {turn.text}"
        for turn in lead.conversation
    )
    user_content = f"Transcript:\n{transcript}\n\nChannel: {lead.channel}"

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=512,
            timeout=TIMEOUT_SECONDS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text.strip()

        # Defensively strip any accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```", 1)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]

        data = json.loads(raw.strip())
        return ExtractedSignals(**data, raw_channel=lead.channel)

    except Exception:
        # Any failure — timeout, API error, JSON parse error, Pydantic validation error
        return None
```

---

## `lib/fallback.py` — Keyword-Based Fallback Scorer

No LLM. Assembles `ExtractedSignals` from keywords, then calls `compute_score`.

```python
import re
from lib.models import ExtractedSignals, LeadInput, ScoredOutput
from lib.scorer import compute_score

PORTFOLIO_KEYWORDS = ["coca-cola", "coke", "monster energy", "monster", "red bull", "fanta", "sprite", "powerade"]
CONSUMER_KEYWORDS = ["office party", "few cans", "personal use", "home", "small quantity", "just want", "retail customer"]
LICENSE_VALID_KEYWORDS = ["licensed", "import license", "licensed importer", "license number", "our license"]
LICENSE_PENDING_KEYWORDS = ["license in process", "license pending", "applying for license", "expected in", "6 weeks", "license soon"]


def fallback_score(lead: LeadInput) -> ScoredOutput:
    """Keyword-based scorer. Always returns a valid ScoredOutput."""
    full_text = " ".join(t.text.lower() for t in lead.conversation)

    is_consumer = any(kw in full_text for kw in CONSUMER_KEYWORDS)

    volume = None
    fcl_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:fcl|container|containers)', full_text)
    if fcl_match:
        volume = float(fcl_match.group(1))

    if any(kw in full_text for kw in LICENSE_VALID_KEYWORDS):
        license_status = "valid"
    elif any(kw in full_text for kw in LICENSE_PENDING_KEYWORDS):
        license_status = "in_process"
    else:
        license_status = "unclear"

    product_fit = any(kw in full_text for kw in PORTFOLIO_KEYWORDS)

    years_match = re.search(r'(\d+)\s*years?\s*(?:importing|import|experience)', full_text)
    years = int(years_match.group(1)) if years_match else None

    accounts_match = re.search(r'(\d+)\s*(?:retail\s*)?accounts?', full_text)
    accounts = int(accounts_match.group(1)) if accounts_match else None

    signals = ExtractedSignals(
        volume_fcl_per_month=volume,
        license_status=license_status,
        product_fit=product_fit,
        years_importing=years,
        retail_accounts=accounts,
        existing_brands=None,
        is_consumer=is_consumer,
        raw_channel=lead.channel,
    )
    return compute_score(signals, lead.lead_id)
```

---

## `api/score.py` — Vercel Entry Point

Vercel Python serverless functions use a class named `handler` inheriting from `BaseHTTPRequestHandler`.

```python
from http.server import BaseHTTPRequestHandler
import json
import os

from lib.models import LeadInput, ScoredOutput
from lib.extractor import extract_signals
from lib.scorer import compute_score
from lib.fallback import fallback_score


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        # 1. Read body
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        # 2. Parse JSON
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as e:
            self._json(400, {"error": "Invalid JSON", "detail": str(e)})
            return

        # 3. Validate input structure
        try:
            lead = LeadInput(**data)
        except Exception as e:
            self._json(400, {"error": "Invalid input schema", "detail": str(e)})
            return

        # 4. Handle empty conversation gracefully
        if not lead.conversation:
            result = ScoredOutput(
                lead_id=lead.lead_id,
                score=0,
                tier="Cold",
                routing="auto_archive",
                reasoning="No conversation content provided — insufficient data to score.",
            )
            self._json(200, result.model_dump())
            return

        # 5. LLM extraction → deterministic scoring, with keyword fallback
        signals = extract_signals(lead)
        if signals is not None:
            result = compute_score(signals, lead.lead_id)
        else:
            result = fallback_score(lead)

        self._json(200, result.model_dump())

    def do_GET(self):
        self._json(200, {
            "service": "ncb-lead-scoring-agent",
            "version": "1.0.0",
            "status": "ok",
            "usage": "POST /api/score with {lead_id, channel, conversation[]}",
        })

    def log_message(self, format, *args):
        pass  # Suppress default access logs in Vercel

    def _json(self, status: int, body: dict):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
```

---

## `vercel.json`

```json
{
  "functions": {
    "api/score.py": {
      "maxDuration": 30
    }
  }
}
```

**Critical:** without `maxDuration`, Vercel Hobby defaults to ~10s. The LLM call will intermittently time out and the endpoint will 504. This config is mandatory.

---

## `requirements.txt`

```
anthropic>=0.40.0
pydantic>=2.0.0
```

---

## `.env.example`

```
ANTHROPIC_API_KEY=your_key_here
```

---

## `.gitignore`

```
.env
__pycache__/
*.pyc
.venv/
.pytest_cache/
```

---

## `tests/test_scorer.py`

Write unit tests that cover the following cases. Import `compute_score` and `ExtractedSignals` directly — no LLM calls in tests.

```python
from lib.models import ExtractedSignals
from lib.scorer import compute_score


def signals(**kwargs) -> ExtractedSignals:
    defaults = dict(
        volume_fcl_per_month=None,
        license_status="unclear",
        product_fit=True,
        years_importing=None,
        retail_accounts=None,
        existing_brands=None,
        is_consumer=False,
        raw_channel="whatsapp",
    )
    defaults.update(kwargs)
    return ExtractedSignals(**defaults)


def test_hot_lead_uae_distributor():
    """S001: UAE distributor, 3 FCL, 8 years, 250 accounts, valid license."""
    s = signals(
        volume_fcl_per_month=2.5,
        license_status="valid",
        years_importing=8,
        retail_accounts=250,
        existing_brands=1,
    )
    result = compute_score(s, "S001")
    assert result.score >= 70
    assert result.tier == "Hot"
    assert result.routing == "kam_handoff"


def test_cold_consumer_request():
    """S002: 'few cans for office party' — consumer, auto-archive."""
    s = signals(is_consumer=True)
    result = compute_score(s, "S002")
    assert result.score == 0
    assert result.tier == "Cold"
    assert result.routing == "auto_archive"


def test_warm_license_in_process():
    """S003: Ghana distributor, license in process, 1 FCL/month."""
    s = signals(
        volume_fcl_per_month=1.0,
        license_status="in_process",
        product_fit=False,
    )
    result = compute_score(s, "S003")
    assert result.tier == "Warm"
    assert result.routing == "nurture_pool"


def test_conflicting_signals_high_volume_no_license():
    """High volume but explicitly no license — must not score Hot."""
    s = signals(
        volume_fcl_per_month=5.0,
        license_status="none",
    )
    result = compute_score(s, "TEST")
    assert result.tier != "Hot"
    assert result.score < 70


def test_empty_conversation_handled_in_api(tmp_path):
    """Verify scorer handles zero-signal edge case without exception."""
    s = signals(
        volume_fcl_per_month=None,
        license_status="unclear",
        product_fit=False,
    )
    result = compute_score(s, "EMPTY")
    assert result.score >= 0
    assert result.tier in ("Hot", "Warm", "Cold")


def test_reasoning_is_non_empty():
    s = signals(license_status="valid", volume_fcl_per_month=2.0)
    result = compute_score(s, "R001")
    assert len(result.reasoning) > 10
```

Run with: `python -m pytest tests/ -v`

---

## `README.md` — Target ~200 Words

Write in natural prose (no AI-sounding bullets). Cover:

1. **What this is:** One-paragraph overview of the endpoint and what it does.

2. **Model and why:** `claude-haiku-4-5-20251001`. Fast enough to stay within the 30s budget, cheap enough to handle high inbound volume across 60+ countries, and fully capable of structured extraction from short transcripts. Frontier models would add latency and cost without meaningful accuracy gain on a structured extraction task.

3. **Scoring logic:** Describe the hybrid architecture: LLM extracts signals, deterministic Python scores them. List the four dimensions and max points. Explain that license is weighted highest (30 pts) because unverified leads have near-zero conversion regardless of volume. Volume is equally weighted because container-load commitment signals real wholesale intent.

4. **Failure handling:** LLM failures fall back to keyword-based scoring. The endpoint always returns valid JSON. Input validation returns 400 for malformed requests; empty conversations return a Cold result gracefully.

5. **With more time:** Labeled eval set from real KAM outcomes to calibrate tier thresholds. Confidence score on borderline leads for human review. Multi-language extraction support. Deduplication of repeat leads. Structured logging to S3 for audit trail and future fine-tuning.

6. **Time spent:** [fill in actual hours]

---

## Deployment Steps (for reference)

```bash
# 1. Install Vercel CLI
npm i -g vercel

# 2. Set env var
vercel env add ANTHROPIC_API_KEY

# 3. Deploy
vercel --prod

# 4. Test manually
curl -X POST https://<your-url>/api/score \
  -H "Content-Type: application/json" \
  -d '{"lead_id":"S001","channel":"whatsapp","conversation":[{"role":"lead","text":"UAE distributor, 3 FCL/month Red Bull, 8 years importing. 250 retail accounts."},{"role":"agent","text":"Volume target?"},{"role":"lead","text":"2-3 FCL/month sustained."}]}'
```

---

## Build Order for Claude Code

Execute in this exact sequence:

1. `lib/__init__.py` (empty file)
2. `lib/models.py`
3. `lib/scorer.py` — implement `compute_score()` and `build_reasoning()` per spec
4. `lib/fallback.py`
5. `lib/extractor.py`
6. `api/score.py`
7. `vercel.json`, `requirements.txt`, `.env.example`, `.gitignore`
8. `tests/test_scorer.py` — run and verify all pass before continuing
9. `README.md`

---

## Pre-Submission Checklist

Before deploying, verify all of these:

- [ ] `POST /api/score` returns valid JSON (not 5xx) for S001, S002, S003
- [ ] S001 → `tier = "Hot"`, `routing = "kam_handoff"`
- [ ] S002 → `tier = "Cold"`, `routing = "auto_archive"`
- [ ] S003 → `tier = "Warm"`, `routing = "nurture_pool"`
- [ ] `vercel.json` has `maxDuration: 30` set for `api/score.py`
- [ ] `ANTHROPIC_API_KEY` is set via Vercel env vars, **not** committed to the repo
- [ ] `.env` is in `.gitignore`
- [ ] `python -m pytest tests/ -v` passes locally
- [ ] `GET /api/score` returns a health/usage JSON (not 404)
- [ ] README covers: model choice, scoring weights, failure handling, what you'd do with more time, hours spent
- [ ] Fallback scorer is reachable code — not dead code — test it by temporarily commenting out the extractor