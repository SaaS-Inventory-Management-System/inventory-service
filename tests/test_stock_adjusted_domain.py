from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.projections import StockBalanceProjector
from app.domain.entities import StockBalance
from app.domain.events import StockAdjusted


def make_adjustment(tenant, article, location, counted_quantity="5", **kwargs):
    return StockAdjusted(
        id=uuid4(),
        tenant_id=tenant,
        article_id=article,
        location_id=location,
        counted_quantity=Decimal(counted_quantity),
        occurred_at=datetime.now(timezone.utc),
        reason=kwargs.pop("reason", "Physical inventory count"),
        **kwargs,
    )


@pytest.mark.parametrize("quantity", ["-0.01", "-5", "NaN", "Infinity", "-Infinity"])
def test_adjusted_event_rejects_negative_or_nonfinite_quantity(quantity):
    with pytest.raises(ValueError, match="[Qq]uantity"):
        make_adjustment(uuid4(), uuid4(), uuid4(), counted_quantity=quantity)


@pytest.mark.parametrize("reason", ["", "   ", "\t  \n"])
def test_adjusted_event_requires_nonblank_reason(reason):
    with pytest.raises(ValueError, match="Reason"):
        make_adjustment(uuid4(), uuid4(), uuid4(), reason=reason)


def test_adjusted_event_allows_zero_and_preserves_metadata():
    tenant, article, location = uuid4(), uuid4(), uuid4()
    event = make_adjustment(
        tenant, article, location, counted_quantity="0",
        reason="Counted zero items", reference="INV-2026-001",
    )
    assert event.counted_quantity == Decimal("0")
    assert event.tenant_id == tenant
    assert event.article_id == article
    assert event.location_id == location
    assert event.reason == "Counted zero items"
    assert event.reference == "INV-2026-001"
    assert event.occurred_at.utcoffset().total_seconds() == 0
    with pytest.raises(FrozenInstanceError):
        event.counted_quantity = Decimal("100")


@pytest.mark.parametrize("counted_quantity", ["0", "7.25"])
def test_projector_creates_stock_balance_without_previous_record(counted_quantity):
    tenant, article, location = uuid4(), uuid4(), uuid4()
    event = make_adjustment(tenant, article, location, counted_quantity)

    projected = StockBalanceProjector().apply(balance=None, event=event)

    assert projected == StockBalance(
        tenant_id=tenant,
        article_id=article,
        location_id=location,
        quantity=Decimal(counted_quantity),
    )


@pytest.mark.parametrize(
    ("before", "after"),
    [("100", "92"), ("10", "15.5"), ("10", "0"), ("10", "10")],
)
def test_projector_sets_absolute_quantity_and_preserves_original(before, after):
    tenant, article, location = uuid4(), uuid4(), uuid4()
    original = StockBalance(tenant, article, location, Decimal(before))
    event = make_adjustment(tenant, article, location, after)

    projected = StockBalanceProjector().apply(balance=original, event=event)

    assert projected.quantity == Decimal(after)
    assert projected is not original
    assert original.quantity == Decimal(before)
    assert (projected.tenant_id, projected.article_id, projected.location_id) == (
        tenant, article, location
    )


@pytest.mark.parametrize("field", ["tenant_id", "article_id", "location_id"])
def test_projector_rejects_adjustment_for_different_balance_key(field):
    tenant, article, location = uuid4(), uuid4(), uuid4()
    original = StockBalance(tenant, article, location, Decimal("10"))
    mismatch = replace(original, **{field: uuid4()})
    event = make_adjustment(tenant, article, location, "2")

    with pytest.raises(ValueError, match="same tenant, article, and location"):
        StockBalanceProjector().apply(balance=mismatch, event=event)
    assert mismatch.quantity == Decimal("10")
