"""Unit tests for StockTransferred and StockBalanceProjector.apply_transfer."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.projections import StockBalanceProjector
from app.domain.entities import StockBalance
from app.domain.errors import InsufficientStockError
from app.domain.events import StockTransferred


def make_event(tenant, article, source, destination, quantity="5", **kwargs):
    return StockTransferred(
        id=uuid4(),
        tenant_id=tenant,
        article_id=article,
        from_location_id=source,
        to_location_id=destination,
        quantity=Decimal(quantity),
        occurred_at=datetime.now(timezone.utc),
        **kwargs,
    )


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "-Infinity"])
def test_transfer_event_rejects_invalid_quantity(quantity):
    with pytest.raises(ValueError):
        make_event(uuid4(), uuid4(), uuid4(), uuid4(), quantity)


def test_transfer_event_requires_different_locations():
    location = uuid4()
    with pytest.raises(ValueError):
        make_event(uuid4(), uuid4(), location, location)


def test_transfer_event_rejects_blank_reason():
    with pytest.raises(ValueError):
        make_event(uuid4(), uuid4(), uuid4(), uuid4(), reason="   ")


def test_transfer_event_optional_metadata_and_immutability():
    event = make_event(uuid4(), uuid4(), uuid4(), uuid4(), "2")
    assert event.reason is None
    assert event.reference is None
    with pytest.raises(FrozenInstanceError):
        event.quantity = Decimal("20")


def test_projector_updates_both_balances_without_mutating_originals():
    tenant, article, source, destination = uuid4(), uuid4(), uuid4(), uuid4()
    original_source = StockBalance(tenant, article, source, Decimal("40"))
    original_destination = StockBalance(tenant, article, destination, Decimal("7.5"))
    event = make_event(tenant, article, source, destination, "12.5")

    new_source, new_destination = StockBalanceProjector().apply_transfer(
        original_source, original_destination, event
    )

    assert new_source.quantity == Decimal("27.5")
    assert new_destination.quantity == Decimal("20")
    assert original_source.quantity == Decimal("40")
    assert original_destination.quantity == Decimal("7.5")
    assert new_source is not original_source
    assert new_destination is not original_destination
    assert new_source.quantity + new_destination.quantity == Decimal("47.5")


def test_projector_creates_destination_balance_when_missing():
    tenant, article, source, destination = uuid4(), uuid4(), uuid4(), uuid4()
    original_source = StockBalance(tenant, article, source, Decimal("10"))
    event = make_event(tenant, article, source, destination, "3")

    new_source, new_destination = StockBalanceProjector().apply_transfer(
        original_source, None, event
    )

    assert new_source.quantity == Decimal("7")
    assert new_destination == StockBalance(tenant, article, destination, Decimal("3"))


def test_projector_allows_transfer_of_entire_source_stock():
    tenant, article, source, destination = uuid4(), uuid4(), uuid4(), uuid4()
    original_source = StockBalance(tenant, article, source, Decimal("8"))
    event = make_event(tenant, article, source, destination, "8")

    new_source, new_destination = StockBalanceProjector().apply_transfer(
        original_source, None, event
    )

    assert new_source.quantity == Decimal("0")
    assert new_destination.quantity == Decimal("8")


def test_projector_rejects_missing_source_balance():
    tenant, article, source, destination = uuid4(), uuid4(), uuid4(), uuid4()
    event = make_event(tenant, article, source, destination, "1")

    with pytest.raises(InsufficientStockError):
        StockBalanceProjector().apply_transfer(None, None, event)


def test_projector_rejects_insufficient_source_balance():
    tenant, article, source, destination = uuid4(), uuid4(), uuid4(), uuid4()
    original_source = StockBalance(tenant, article, source, Decimal("3"))
    original_destination = StockBalance(tenant, article, destination, Decimal("10"))
    event = make_event(tenant, article, source, destination, "4")

    with pytest.raises(InsufficientStockError):
        StockBalanceProjector().apply_transfer(
            original_source, original_destination, event
        )

    assert original_source.quantity == Decimal("3")
    assert original_destination.quantity == Decimal("10")


@pytest.mark.parametrize("field", ["tenant_id", "article_id", "location_id"])
def test_projector_rejects_mismatched_source_balance(field):
    tenant, article, source, destination = uuid4(), uuid4(), uuid4(), uuid4()
    correct = StockBalance(tenant, article, source, Decimal("10"))
    incorrect = replace(correct, **{field: uuid4()})
    event = make_event(tenant, article, source, destination, "2")

    with pytest.raises(ValueError):
        StockBalanceProjector().apply_transfer(incorrect, None, event)


@pytest.mark.parametrize("field", ["tenant_id", "article_id", "location_id"])
def test_projector_rejects_mismatched_destination_balance(field):
    tenant, article, source, destination = uuid4(), uuid4(), uuid4(), uuid4()
    original_source = StockBalance(tenant, article, source, Decimal("10"))
    correct_destination = StockBalance(tenant, article, destination, Decimal("5"))
    incorrect_destination = replace(correct_destination, **{field: uuid4()})
    event = make_event(tenant, article, source, destination, "2")

    with pytest.raises(ValueError):
        StockBalanceProjector().apply_transfer(
            original_source, incorrect_destination, event
        )
