from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.projections import StockBalanceProjector
from app.domain.entities import StockBalance
from app.domain.events import StockReceived

from app.infrastructure.repositories.in_memory import (
    InMemoryStockEventRepository,
    InMemoryStockBalanceRepository,
)


def make_event(tenant_id=None, article_id=None, location_id=None, quantity="10"):
    return StockReceived(
        id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        article_id=article_id or uuid4(),
        location_id=location_id or uuid4(),
        quantity=Decimal(quantity),
        occurred_at=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "-Infinity"])
def test_stock_received_rejects_invalid_quantity(quantity):
    with pytest.raises(ValueError):
        make_event(quantity=quantity)


@pytest.mark.parametrize("quantity", ["-1", "NaN", "Infinity", "-Infinity"])
def test_stock_balance_rejects_invalid_quantity(quantity):
    with pytest.raises(ValueError):
        StockBalance(uuid4(), uuid4(), uuid4(), Decimal(quantity))


def test_zero_balance_is_valid():
    balance = StockBalance(uuid4(), uuid4(), uuid4(), Decimal("0"))
    assert balance.quantity == Decimal("0")


def test_projector_creates_initial_balance_and_new_immutable_balance():
    event = make_event(quantity="12.5")
    projector = StockBalanceProjector()

    first = projector.apply(None, event)
    assert first.tenant_id == event.tenant_id
    assert first.article_id == event.article_id
    assert first.location_id == event.location_id
    assert first.quantity == Decimal("12.5")

    second_event = make_event(
        tenant_id=event.tenant_id,
        article_id=event.article_id,
        location_id=event.location_id,
        quantity="2.5",
    )
    second = projector.apply(first, second_event)

    assert first.quantity == Decimal("12.5")
    assert second.quantity == Decimal("15.0")
    assert second is not first
    with pytest.raises(FrozenInstanceError):
        first.quantity = Decimal("999")


@pytest.mark.parametrize("field", ["tenant_id", "article_id", "location_id"])
def test_projector_refuses_event_for_different_balance(field):
    event = make_event()
    balance = StockBalance(
        event.tenant_id, event.article_id, event.location_id, Decimal("10")
    )
    different_balance = replace(balance, **{field: uuid4()})

    with pytest.raises(ValueError):
        StockBalanceProjector().apply(different_balance, event)


def test_event_repository_keeps_order_and_filters_by_all_ids():
    repo = InMemoryStockEventRepository()
    tenant, article, location = uuid4(), uuid4(), uuid4()
    first = make_event(tenant, article, location, "5")
    foreign_location = make_event(tenant, article, uuid4(), "99")
    foreign_tenant = make_event(uuid4(), article, location, "99")
    second = make_event(tenant, article, location, "7")

    for event in (first, foreign_location, foreign_tenant, second):
        repo.append(event)

    assert repo.list_events(tenant, article, location) == [first, second]


def test_event_repository_rejects_duplicate_event_id():
    repo = InMemoryStockEventRepository()
    event = make_event()
    repo.append(event)

    with pytest.raises(ValueError):
        repo.append(event)

    assert repo.list_events(event.tenant_id, event.article_id, event.location_id) == [
        event
    ]


def test_balance_repository_saves_and_replaces_by_composite_key():
    repo = InMemoryStockBalanceRepository()
    balance = StockBalance(uuid4(), uuid4(), uuid4(), Decimal("10"))
    assert repo.get_by_ids(balance.tenant_id, balance.article_id, balance.location_id) is None

    repo.save(balance)
    updated = replace(balance, quantity=Decimal("25"))
    repo.save(updated)

    assert repo.get_by_ids(balance.tenant_id, balance.article_id, balance.location_id) == updated
    assert repo.get_by_ids(uuid4(), balance.article_id, balance.location_id) is None
    assert repo.get_by_ids(balance.tenant_id, balance.article_id, uuid4()) is None


def test_rebuild_balance_from_event_history():
    tenant_id, article_id, location_id = uuid4(), uuid4(), uuid4()
    events = InMemoryStockEventRepository()
    for quantity in ("100", "25", "2.5"):
        events.append(make_event(tenant_id, article_id, location_id, quantity))

    current = None
    projector = StockBalanceProjector()
    for event in events.list_events(tenant_id, article_id, location_id):
        current = projector.apply(current, event)

    assert current is not None
    assert current.quantity == Decimal("127.5")
