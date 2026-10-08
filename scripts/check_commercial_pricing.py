"""Preflight for AETHRON's published commercial price schedule and buyer documents.

This validates documentation integrity only. It cannot certify contract enforceability.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "commercial"
MARKDOWN_FILES = [
    ROOT / "COMMERCIAL-LICENSING.md",
    ROOT / "LICENSING.md",
    DOC / "FAQ.md",
    DOC / "SUPPORT-AND-BILLING.md",
    DOC / "OWNER-OPERATIONS.md",
    DOC / "ORDER-FORM-TEMPLATE.md",
    DOC / "COMMERCIAL-LICENSE-AGREEMENT-TEMPLATE.md",
]
EXPECTED_PLANS = {
    "community": (0, None, None),
    "indie": (199, 1, 1),
    "startup": (499, 5, 1),
    "small_business": (990, 10, 3),
    "business": (2490, 25, 5),
    "oem_enterprise": (4900, "negotiated", "negotiated"),
}


def check():
    """Raise AssertionError for any missing/corrupt or inconsistent policy item."""
    data = json.loads((DOC / "plans.json").read_text(encoding="utf-8"))
    assert data["currency"] == "EUR"
    assert data["community_license"] == "GPL-3.0-only"
    assert data["contract_required"] is True
    assert data["automated_checkout_available"] is False
    assert data["offline_activation_required"] is False
    assert data["software_qualified_for_automotive_or_uas"] is False
    assert data["default_annual_term_months"] == 12
    assert data["auto_renewal_default"] is False

    plans = {p["id"]: p for p in data["plan_definitions"]}
    assert set(plans) == set(EXPECTED_PLANS)
    for key, (price, devs, products) in EXPECTED_PLANS.items():
        p = plans[key]
        assert p["annual_price_eur"] == price, key
        assert p["developers"] == devs, key
        assert p["product_families"] == products, key
        if key not in ("community", "oem_enterprise"):
            assert p["deployments"] == "unlimited_named_products", key
            assert p["per_device_fee_eur"] == 0, key

    founding = data["founding"]
    assert (founding["annual_price_eur"], founding["maximum_customers"]) == (499, 25)
    assert (founding["developer_seats"], founding["product_families"]) == (10, 3)
    assert founding["fixed_annual_periods"] == 3
    assert founding["signed_order_allocates_slot"] is True
    assert founding["slots_claimed"] is None  # Do not invent live inventory.

    support = data["support"]
    assert support["priority_per_month_eur"] == 99
    assert support["priority_new_tickets_per_month"] == 5
    assert support["priority_reply_target_swedish_business_days"] == 2
    assert (support["engineering_min_hourly_eur"], support["engineering_max_hourly_eur"]) == (
        125,
        175,
    )
    assert support["certified_sla_included"] is False
    assert data["rules"]["no_mandatory_online_activation"] is True

    page = (ROOT / "web" / "public" / "commercial.html").read_text(encoding="utf-8")
    plan_md = (ROOT / "COMMERCIAL-LICENSING.md").read_text(encoding="utf-8")
    faq = (DOC / "FAQ.md").read_text(encoding="utf-8")
    contract = (DOC / "COMMERCIAL-LICENSE-AGREEMENT-TEMPLATE.md").read_text(encoding="utf-8")
    order = (DOC / "ORDER-FORM-TEMPLATE.md").read_text(encoding="utf-8")
    support_md = (DOC / "SUPPORT-AND-BILLING.md").read_text(encoding="utf-8")

    for key, p in plans.items():
        assert p["name"] in plan_md or (key == "community" and "Community (GPLv3)" in plan_md), (
            "pricing_md",
            key,
        )
        assert p["name"] in page or (
            key in {"community", "indie", "startup"} and p["name"].split()[0] in page
        ), ("web", key)
        if key == "community":
            assert "€0" in plan_md
        else:
            formatted = "€" + format(p["annual_price_eur"], ",")
            assert formatted in plan_md, ("price_md", key)
            assert formatted in page, ("price_web", key)

    for phrase in [
        "€499",
        "25",
        "three",
        "10 developers",
        "3 product",
        "Unlimited",
        "royalty",
        "GPLv3",
        "VAT",
    ]:
        assert phrase.lower() in plan_md.lower(), ("commercial_price", phrase)

    for phrase in [
        "not automatically",
        "signed agreement",
        "third-party",
        "No automatic renewal",
        "30 calendar days",
        "perpetual",
        "material breach",
        "research-stage",
    ]:
        assert phrase.lower() in contract.lower(), ("agreement", phrase)

    for phrase in ["F001", "F025", "signed", "EUR", "VAT"]:
        assert phrase in order, ("order", phrase)

    for phrase in ["€99/month", "€125–175/hour", "best effort", "manual"]:
        assert phrase.lower() in support_md.lower(), ("support", phrase)

    assert "online" in faq.lower() and "renewal" in faq.lower()
    assert "no mandatory cloud activation" in page.lower()
    assert "not safety certification" in page.lower()
    assert (
        "licence" in (ROOT / "README.md").read_text(encoding="utf-8").lower()
        or "licensing" in (ROOT / "README.md").read_text(encoding="utf-8").lower()
    )
    assert 'href="./commercial.html"' in (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "<script" not in page.lower()  # The informational page has no tracking/payment JS.
    assert 'http-equiv="refresh"' not in page.lower()

    for md in MARKDOWN_FILES:
        assert md.is_file(), md
        body = md.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", body):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            local = (md.parent / target.split("#", 1)[0]).resolve()
            assert local.exists(), (md.relative_to(ROOT), target)
            assert str(local).startswith(str(ROOT)), (md, target)

    assert "GNU GENERAL PUBLIC LICENSE" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    print(
        "PASS: commercial pricing, founding programme, offline rights, document links and safety disclaimers"
    )


if __name__ == "__main__":
    check()
