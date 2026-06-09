import json
import os
import openai
from lib.models import ExtractedSignals, LeadInput

_client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=18)
MODEL = "gpt-4o-mini"

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


def extract_signals(lead: LeadInput) -> ExtractedSignals | None:
    """
    Call GPT-4o mini to extract structured signals from the conversation.
    Returns None on any failure — caller must invoke fallback_score().
    """
    transcript = "\n".join(
        f"[{turn.role.upper()}]: {turn.text}"
        for turn in lead.conversation
    )
    user_content = f"Transcript:\n{transcript}\n\nChannel: {lead.channel}"

    try:
        response = _client.chat.completions.create(
            model=MODEL,
            max_tokens=512,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        raw = response.choices[0].message.content.strip()

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
