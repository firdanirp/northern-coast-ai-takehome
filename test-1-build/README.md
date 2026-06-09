# NCB Lead Scoring Agent

A deployed Vercel HTTP endpoint that accepts a B2B beverage distributor conversation transcript and returns a scored routing decision — determining whether an inbound lead should go to a Key Account Manager, enter a nurture pool, or be auto-archived.

## Model and Why

The extraction step uses `gpt-4o-mini`. It is fast enough (typically under 3s) to stay comfortably within the 30-second Vercel budget, and cheap enough to handle high inbound volume across Northern Coast's 60+ country footprint. The extraction task — pulling seven structured fields from a short conversation — is well within its capabilities. A frontier model would add meaningful latency and cost without improving accuracy on a structured-extraction task with a tight schema and explicit extraction rules.

## Scoring Logic

The architecture is hybrid: Claude Haiku extracts signals from the conversation into structured fields, then a pure Python function deterministically converts those fields into a score. The LLM never outputs a number. This makes scores reproducible, auditable, and resistant to prompt injection.

Scoring is across four dimensions (100 points total):

- **License status** (30 pts): Highest weight because a lead without a verified import license has near-zero conversion regardless of stated volume — chasing unlicensed prospects wastes KAM time.
- **Volume** (30 pts): Container-load commitment signals real wholesale intent. Equally weighted to license because a licensed importer ordering half a pallet is not a KAM-worthy account.
- **Product fit** (20 pts): Whether a portfolio brand (Coca-Cola, Monster, Red Bull, etc.) is explicitly named.
- **Business signals** (20 pts): Years importing, retail account count, and existing brand count — proxy indicators of operational maturity.

Tier thresholds: ≥70 → Hot (KAM handoff), 35–69 → Warm (nurture pool), <35 → Cold (auto-archive). Consumer or personal-use requests are immediately scored 0 and archived regardless of other signals.

## Failure Handling

If the LLM call fails for any reason — network timeout, API error, unparseable JSON, validation failure — the endpoint falls back to a keyword-based scorer that assembles signals from regex patterns and keyword lists, then runs the same deterministic scoring function. The endpoint always returns valid JSON; it will never return a 5xx to the caller. Input validation returns 400 for malformed requests, and an empty conversation returns a Cold result gracefully rather than erroring.

## With More Time

A labeled eval set built from real KAM outcomes would let us calibrate the tier thresholds empirically rather than by intuition. Borderline leads (scores near 35 or 70) would benefit from a confidence flag that routes them to human review rather than hard classification. Multi-language extraction support matters given the 60+ country scope — the system prompt currently assumes English. Deduplication of repeat leads would prevent the same prospect from re-entering the KAM queue. Structured logging to S3 would create an audit trail and a dataset for future fine-tuning.

## Time Spent

~1.5 hours.

## Local Development

```bash
cp .env.example .env
# add your ANTHROPIC_API_KEY to .env

pip install -r requirements.txt
python -m pytest tests/ -v
```

## Deployment

```bash
npm i -g vercel
vercel env add OPENAI_API_KEY
vercel --prod
```

## Test the Endpoint

```bash
# Hot lead
curl -X POST https://<your-url>/api/score \
  -H "Content-Type: application/json" \
  -d '{"lead_id":"S001","channel":"whatsapp","conversation":[{"role":"lead","text":"UAE distributor, 3 FCL/month Red Bull, 8 years importing. 250 retail accounts."},{"role":"agent","text":"Volume target?"},{"role":"lead","text":"2-3 FCL/month sustained. We are fully licensed."}]}'

# Consumer (auto-archive)
curl -X POST https://<your-url>/api/score \
  -H "Content-Type: application/json" \
  -d '{"lead_id":"S002","channel":"email","conversation":[{"role":"lead","text":"Hi just want a few cans for an office party"}]}'
```
