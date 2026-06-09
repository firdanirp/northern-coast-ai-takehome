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
