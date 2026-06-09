# Test 1 — Build a deployed lead-scoring agent

You're applying for a senior AI Platform Engineer role at Northern Coast Beverages. This is the first of two technical tests. It evaluates **AI tool fluency** — can you ship working agent infrastructure quickly using modern AI tooling?

## What to build

A deployed HTTP endpoint at a publicly-reachable URL that accepts a JSON conversation transcript and returns a scored routing decision.

## Input contract (we POST this)

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

## Output contract (your endpoint returns)

```json
{
  "lead_id": "L001",
  "score": 78,
  "tier": "Warm",
  "routing": "kam_handoff",
  "reasoning": "Licensed importer, moderate volume single-brand focus — eligible for KAM follow-up."
}
```

Fields:
- `score`: integer 0-100
- `tier`: "Hot" | "Warm" | "Cold"
- `routing`: "kam_handoff" | "nurture_pool" | "auto_archive"
- `reasoning`: 1-2 sentence rationale

## Requirements

1. Deployed at a publicly-reachable Vercel URL (free tier is fine)
2. Accepts the input JSON via POST
3. Returns the output JSON within 30 seconds
4. Code repo URL also provided
5. Brief README (~200 words): what model, why, what would you do with more time

## Sample payloads to test against

Three samples to iterate against. **We'll evaluate against three different payloads** (similar shape, possibly trickier).

### Hot example

```json
{
  "lead_id": "S001",
  "channel": "whatsapp",
  "conversation": [
    {"role": "lead", "text": "UAE distributor, 3 FCL/month Red Bull, 8 years importing energy drinks. Looking for original Austrian product."},
    {"role": "agent", "text": "Volume target on Red Bull specifically?"},
    {"role": "lead", "text": "2-3 FCL/month sustained. ~250 retail accounts across UAE."}
  ]
}
```

### Cold example

```json
{
  "lead_id": "S002",
  "channel": "email",
  "conversation": [
    {"role": "lead", "text": "hey can I get a few cans of red bull for my office party"}
  ]
}
```

### Ambiguous example

```json
{
  "lead_id": "S003",
  "channel": "email",
  "conversation": [
    {"role": "lead", "text": "Ghana-based distributor looking for Coca-Cola products. New entrant, license in process — expected 6 weeks. Initial volume 1 FCL/month."}
  ]
}
```

## Business context (light — you fill in the rest)

Northern Coast is a B2B beverage distributor (Coca-Cola, Monster, Red Bull, etc.). Inbound leads from wholesalers in 60+ countries. Container-load orders ($30K-$100K). The scoring intuition: import license + product fit + volume (≥1 FCL/month) + real-business signals.

Hot = ready for a KAM call. Warm = nurture pool. Cold = auto-archive.

You define the specifics of scoring weights. Defend your choices in the README.

## Time

~2 hours suggested. If you spend significantly more or less, note it.

## What we'll evaluate

1. **Does it ship?** URL responds correctly to all 3 evaluation payloads with valid JSON.
2. **Code quality** — readable, defensible architecture, sensible model choice
3. **README** — your reasoning, your model choice, what you'd do with more time
4. **Failure handling** — what happens if the input is malformed, the LLM call fails, etc.

## Use AI freely

Claude, Cursor, Codex — whatever you use day-to-day. We assume you'll use AI to write most of the code. We're testing whether you can **direct AI to ship working infrastructure**, not whether you can write Vercel functions from scratch.

## Submission

Reply to this brief with:
- The deployed URL
- The code repo URL (GitHub / GitLab)
- Approximate hours spent
