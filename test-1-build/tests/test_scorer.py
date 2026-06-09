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
