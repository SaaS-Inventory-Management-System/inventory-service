"""Unit tests for the ConsumeStock use case."""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.usecases.stock_events import ConsumeStock, ReceiveStock
from app.application.projections import StockBalanceProjector
from app.domain.entities import Location
from app.domain.errors import InsufficientStockError, LocationNotFoundError
from app.domain.events import StockConsumed
from app.infrastructure.repositories.in_memory import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository,
)


@pytest.fixture
def context():
    tenant, article, location = uuid4(), uuid4(), uuid4()
    locations = InMemoryLocationRepository()
    events = InMemoryStockEventRepository()
    balances = InMemoryStockBalanceRepository()
    locations.save(Location(id=location, tenant_id=tenant, name="Glavno skladišče"))
    dependencies = dict(
        event_repository=events,
        balance_repository=balances,
        location_repository=locations,
        projector=StockBalanceProjector(),
    )
    return {
        "tenant": tenant,
        "article": article,
        "location": location,
        "locations": locations,
        "events": events,
        "balances": balances,
        "receive": ReceiveStock(**dependencies),
        "consume": ConsumeStock(**dependencies),
    }


def test_consumption_updates_balance_and_saves_event_with_metadata(context):
    c = context
    c["receive"](c["tenant"], c["article"], c["location"], Decimal("50"))

    result = c["consume"](
        c["tenant"], c["article"], c["location"],
        Decimal("12.5"), reason="Servis", reference="DN-123",
    )

    assert result.quantity == Decimal("37.5")
    assert c["balances"].get_by_ids(
        c["tenant"], c["article"], c["location"]
    ) == result
    stored = c["events"].list_events(c["tenant"], c["article"], c["location"])
    assert len(stored) == 2
    assert isinstance(stored[-1], StockConsumed)
    assert stored[-1].quantity == Decimal("12.5")
    assert stored[-1].reason == "Servis"
    assert stored[-1].reference == "DN-123"


def test_consumption_without_reason_or_reference_is_allowed(context):
    c = context
    c["receive"](c["tenant"], c["article"], c["location"], Decimal("5"))
    result = c["consume"](c["tenant"], c["article"], c["location"], Decimal("5"))

    assert result.quantity == Decimal("0")
    event = c["events"].list_events(c["tenant"], c["article"], c["location"])[-1]
    assert event.reason is None
    assert event.reference is None


@pytest.mark.parametrize("amount", ["6", "100"])
def test_insufficient_stock_does_not_record_a_consumption(context, amount):
    c = context
    c["receive"](c["tenant"], c["article"], c["location"], Decimal("5"))

    with pytest.raises(InsufficientStockError):
        c["consume"](c["tenant"], c["article"], c["location"], Decimal(amount))

    assert c["balances"].get_by_ids(
        c["tenant"], c["article"], c["location"]
    ).quantity == Decimal("5")
    assert len(c["events"].list_events(c["tenant"], c["article"], c["location"])) == 1


def test_consumption_without_prior_stock_does_not_write_anything(context):
    c = context
    with pytest.raises(InsufficientStockError):
        c["consume"](c["tenant"], c["article"], c["location"], Decimal("1"))

    assert c["events"].list_events(c["tenant"], c["article"], c["location"]) == []
    assert c["balances"].get_by_ids(c["tenant"], c["article"], c["location"]) is None


def test_missing_or_other_tenants_location_does_not_change_stock(context):
    c = context
    with pytest.raises(LocationNotFoundError):
        c["consume"](c["tenant"], c["article"], uuid4(), Decimal("1"))
    with pytest.raises(LocationNotFoundError):
        c["consume"](uuid4(), c["article"], c["location"], Decimal("1"))

    assert c["events"].list_events(c["tenant"], c["article"], c["location"]) == []
    assert c["balances"].get_by_ids(c["tenant"], c["article"], c["location"]) is None


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity"])
def test_invalid_quantity_does_not_write_event_or_change_balance(context, amount):
    c = context
    c["receive"](c["tenant"], c["article"], c["location"], Decimal("10"))

    with pytest.raises(ValueError):
        c["consume"](c["tenant"], c["article"], c["location"], Decimal(amount))

    assert c["balances"].get_by_ids(
        c["tenant"], c["article"], c["location"]
    ).quantity == Decimal("10")
    assert len(c["events"].list_events(c["tenant"], c["article"], c["location"])) == 1
