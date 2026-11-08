from decimal import Decimal
from uuid import uuid4

import pytest

from app.usecases.stock_event import ReceiveStock
from app.usecases.projections import StockBalanceProjector
from app.domain.entities import Location
from app.domain.errors import LocationNotFoundError
from app.fakes.repositories import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository,
)


@pytest.fixture
def context():
    tenant_id, article_id, location_id = uuid4(), uuid4(), uuid4()
    locations = InMemoryLocationRepository()
    events = InMemoryStockEventRepository()
    balances = InMemoryStockBalanceRepository()
    locations.save(Location(id=location_id, tenant_id=tenant_id, name="Skladišče"))

    receive = ReceiveStock(
        event_repository=events,
        balance_repository=balances,
        location_repository=locations,
        projector=StockBalanceProjector(),
    )
    return receive, locations, events, balances, tenant_id, article_id, location_id


def test_first_receipt_creates_event_and_balance(context):
    receive, _, events, balances, tenant, article, location = context

    result = receive(tenant, article, location, Decimal("50"))

    assert result.quantity == Decimal("50")
    assert balances.get_by_ids(tenant, article, location) == result
    stored_events = events.list_events(tenant, article, location)
    assert len(stored_events) == 1
    assert stored_events[0].quantity == Decimal("50")
    assert stored_events[0].occurred_at.utcoffset().total_seconds() == 0


def test_second_receipt_adds_to_balance_and_keeps_both_events(context):
    receive, _, events, balances, tenant, article, location = context

    receive(tenant, article, location, Decimal("50"))
    result = receive(tenant, article, location, Decimal("12.5"))

    assert result.quantity == Decimal("62.5")
    assert balances.get_by_ids(tenant, article, location).quantity == Decimal("62.5")
    assert [e.quantity for e in events.list_events(tenant, article, location)] == [
        Decimal("50"),
        Decimal("12.5"),
    ]


def test_receipts_in_different_locations_keep_separate_balances(context):
    receive, locations, _, balances, tenant, article, first_location = context
    second_location = uuid4()
    locations.save(Location(id=second_location, tenant_id=tenant, name="Delavnica"))

    receive(tenant, article, first_location, Decimal("50"))
    receive(tenant, article, second_location, Decimal("10"))

    assert balances.get_by_ids(tenant, article, first_location).quantity == Decimal("50")
    assert balances.get_by_ids(tenant, article, second_location).quantity == Decimal("10")


def test_unknown_or_other_tenants_location_does_not_create_event(context):
    receive, _, events, balances, tenant, article, location = context

    with pytest.raises(LocationNotFoundError):
        receive(tenant, article, uuid4(), Decimal("5"))
    with pytest.raises(LocationNotFoundError):
        receive(uuid4(), article, location, Decimal("5"))

    assert events.list_events(tenant, article, location) == []
    assert balances.get_by_ids(tenant, article, location) is None


@pytest.mark.parametrize("quantity", ["0", "-5", "NaN", "Infinity"])
def test_invalid_receipt_neither_writes_event_nor_balance(context, quantity):
    receive, _, events, balances, tenant, article, location = context

    with pytest.raises(ValueError):
        receive(tenant, article, location, Decimal(quantity))

    assert events.list_events(tenant, article, location) == []
    assert balances.get_by_ids(tenant, article, location) is None
