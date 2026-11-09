"""Domain and projection tests for stock consumption and mixed event replay."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.projections import StockBalanceProjector
from app.domain.entities import StockBalance
from app.domain.errors import InsufficientStockError
from app.domain.events import StockConsumed, StockReceived
from app.infrastructure.repositories.in_memory import (
    InMemoryStockEventRepository,
)


def consumed(tenant, article, location, quantity="5", reason=None, reference=None):
    return StockConsumed(
        id=uuid4(),
        tenant_id=tenant,
        article_id=article,
        location_id=location,
        quantity=Decimal(quantity),
        occurred_at=datetime.now(timezone.utc),
        reason=reason,
        reference=reference,
    )


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "-Infinity"])
def test_consumed_rejects_invalid_quantities(quantity):
    with pytest.raises(ValueError):
        consumed(uuid4(), uuid4(), uuid4(), quantity)


def test_consumed_optional_fields_and_immutability():
    event = consumed(uuid4(), uuid4(), uuid4(), "2")
    assert event.reason is None
    assert event.reference is None
    with pytest.raises(FrozenInstanceError):
        event.quantity = Decimal("20")


def test_consumed_rejects_blank_reason_if_provided():
    with pytest.raises(ValueError):
        consumed(uuid4(), uuid4(), uuid4(), "1", reason="   ")


def test_projector_subtracts_consumed_quantity_without_mutating_old_balance():
    tenant, article, location = uuid4(), uuid4(), uuid4()
    balance = StockBalance(tenant, article, location, Decimal("50"))
    event = consumed(tenant, article, location, "12.5")

    updated = StockBalanceProjector().apply(balance, event)

    assert updated.quantity == Decimal("37.5")
    assert balance.quantity == Decimal("50")
    assert updated is not balance


def test_projector_allows_consuming_exactly_the_available_stock():
    tenant, article, location = uuid4(), uuid4(), uuid4()
    balance = StockBalance(tenant, article, location, Decimal("10"))

    updated = StockBalanceProjector().apply(
        balance, consumed(tenant, article, location, "10")
    )
    assert updated.quantity == Decimal("0")


def test_projector_rejects_consumption_when_balance_does_not_exist():
    with pytest.raises(InsufficientStockError):
        StockBalanceProjector().apply(
            None, consumed(uuid4(), uuid4(), uuid4(), "1")
        )


def test_projector_rejects_consumption_above_available_stock():
    tenant, article, location = uuid4(), uuid4(), uuid4()
    balance = StockBalance(tenant, article, location, Decimal("5"))

    with pytest.raises(InsufficientStockError):
        StockBalanceProjector().apply(
            balance, consumed(tenant, article, location, "6")
        )
    assert balance.quantity == Decimal("5")


@pytest.mark.parametrize("field", ["tenant_id", "article_id", "location_id"])
def test_projector_rejects_consumption_for_wrong_balance(field):
    tenant, article, location = uuid4(), uuid4(), uuid4()
    balance = StockBalance(tenant, article, location, Decimal("10"))
    mismatched = replace(balance, **{field: uuid4()})

    with pytest.raises(ValueError):
        StockBalanceProjector().apply(
            mismatched, consumed(tenant, article, location, "2")
        )


def test_replay_of_mixed_receipt_and_consumption_events_restores_balance():
    """Event Store is the source of truth; rebuild a fresh read model."""
    tenant, article, location = uuid4(), uuid4(), uuid4()
    events = InMemoryStockEventRepository()
    events.append(
        StockReceived(
            id=uuid4(), tenant_id=tenant, article_id=article,
            location_id=location, quantity=Decimal("100"),
            occurred_at=datetime.now(timezone.utc),
        )
    )
    events.append(consumed(tenant, article, location, "30", reason="Delo"))
    events.append(consumed(tenant, article, location, "20"))

    stored_events = events.list_events(tenant, article, location)
    assert len(stored_events) == 3
    assert isinstance(stored_events[1], StockConsumed)

    rebuilt_balance = None
    projector = StockBalanceProjector()
    for event in stored_events:
        rebuilt_balance = projector.apply(rebuilt_balance, event)

    assert rebuilt_balance is not None
    assert rebuilt_balance.quantity == Decimal("50")
