from app.services.commerce import (
    FREE_RESUME_AI_LIMIT,
    FREE_RESUME_LIMIT,
    PLANS,
    TOTAL_RESUME_LIMIT,
)


def test_fixed_membership_prices_and_entitlement_limits():
    assert set(PLANS) == {"membership_monthly", "membership_quarterly"}
    assert PLANS["membership_monthly"]["price_yuan"] == 39
    assert PLANS["membership_monthly"]["days"] == 30
    assert PLANS["membership_quarterly"]["price_yuan"] == 99
    assert PLANS["membership_quarterly"]["days"] == 90
    assert FREE_RESUME_LIMIT == 2
    assert FREE_RESUME_AI_LIMIT == 5
    assert TOTAL_RESUME_LIMIT == 10
