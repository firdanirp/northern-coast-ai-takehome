from lib.models import ExtractedSignals, ScoredOutput


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


def compute_score(signals: ExtractedSignals, lead_id: str) -> ScoredOutput:
    if signals.is_consumer:
        return ScoredOutput(
            lead_id=lead_id,
            score=0,
            tier="Cold",
            routing="auto_archive",
            reasoning=build_reasoning(signals, 0, "Cold"),
        )

    # License points (max 30)
    license_pts = {"valid": 30, "in_process": 13, "none": 0, "unclear": 5}[signals.license_status]

    # Volume points (max 30)
    v = signals.volume_fcl_per_month
    if v is None:
        volume_pts = 5
    elif v >= 3:
        volume_pts = 30
    elif v >= 1:
        volume_pts = 18
    elif v >= 0.5:
        volume_pts = 8
    else:
        volume_pts = 3

    # Product fit points (max 20)
    product_fit_pts = 20 if signals.product_fit else 10

    # Business signals (max 20)
    years_pts = min((signals.years_importing or 0) * 2, 10)
    accounts_pts = min(((signals.retail_accounts or 0) // 50) * 2, 6)
    brands_pts = min((signals.existing_brands or 0) * 2, 4)
    business_pts = years_pts + accounts_pts + brands_pts

    total_score = license_pts + volume_pts + product_fit_pts + business_pts

    if total_score >= 70:
        tier = "Hot"
        routing = "kam_handoff"
    elif total_score >= 35:
        tier = "Warm"
        routing = "nurture_pool"
    else:
        tier = "Cold"
        routing = "auto_archive"

    return ScoredOutput(
        lead_id=lead_id,
        score=total_score,
        tier=tier,
        routing=routing,
        reasoning=build_reasoning(signals, total_score, tier),
    )
