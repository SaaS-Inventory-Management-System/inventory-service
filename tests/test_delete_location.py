"""DeleteLocation: no stock may remain; history remains accessible."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.usecases.location import DeleteLocation
from app.usecases.stock_balance import GetStockHistory, RebuildStockBalances
from app.usecases.projections import StockBalanceProjector
from app.domain.entities import Location, StockBalance
from app.domain.errors import LocationInUseError, LocationNotFoundError
from app.domain.events import StockReceived, StockConsumed
from app.fakes.repositories import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository
)


@pytest.fixture
def context():
    tenant, foreign_tenant, article = uuid4(), uuid4(), uuid4()
    location = Location(id=uuid4(), tenant_id=tenant, name="Skladišče")
    foreign_location = Location(id=uuid4(), tenant_id=foreign_tenant, name="Tuja lokacija")
    locations = InMemoryLocationRepository()
    locations.save(location)
    locations.save(foreign_location)
    balances = InMemoryStockBalanceRepository()
    events = InMemoryStockEventRepository()
    return {
        "tenant": tenant,
        "foreign_tenant": foreign_tenant,
        "article": article,
        "location": location,
        "foreign_location": foreign_location,
        "locations": locations,
        "balances": balances,
        "events": events,
        "delete": DeleteLocation(locations, balances),
    }


def test_can_soft_delete_location_without_any_balances(context):
    c = context
    result = c["delete"](c["tenant"], c["location"].id)

    assert result is None
    assert c["locations"].get_by_id(c["tenant"], c["location"].id) is None
    old = c["locations"].get_by_id_including_deleted(c["tenant"], c["location"].id)
    assert old is not None and old.deleted_at is not None
    assert c["locations"].list_locations(c["tenant"]) == []


def test_can_soft_delete_when_balance_is_zero(context):
    c = context
    c["balances"].save(StockBalance(
        tenant_id=c["tenant"], article_id=c["article"],
        location_id=c["location"].id, quantity=Decimal("0"),
    ))

    c["delete"](c["tenant"], c["location"].id)
    assert c["locations"].get_by_id(c["tenant"], c["location"].id) is None
    assert c["balances"].get_by_ids(
        c["tenant"], c["article"], c["location"].id
    ).quantity == 0


def test_cannot_delete_location_with_positive_stock(context):
    c = context
    c["balances"].save(StockBalance(
        tenant_id=c["tenant"], article_id=c["article"],
        location_id=c["location"].id, quantity=Decimal("2.5"),
    ))

    with pytest.raises(LocationInUseError):
        c["delete"](c["tenant"], c["location"].id)

    active = c["locations"].get_by_id(c["tenant"], c["location"].id)
    assert active is not None and active.deleted_at is None


def test_cannot_delete_if_one_of_multiple_articles_has_stock(context):
    c = context
    for article, quantity in ((c["article"], "0"), (uuid4(), "1")):
        c["balances"].save(StockBalance(
            tenant_id=c["tenant"], article_id=article,
            location_id=c["location"].id, quantity=Decimal(quantity),
        ))

    with pytest.raises(LocationInUseError):
        c["delete"](c["tenant"], c["location"].id)
    assert c["locations"].get_by_id(c["tenant"], c["location"].id) is not None


def test_cannot_delete_unknown_foreign_or_already_deleted_location(context):
    c = context
    for location_id in (uuid4(), c["foreign_location"].id):
        with pytest.raises(LocationNotFoundError):
            c["delete"](c["tenant"], location_id)

    c["delete"](c["tenant"], c["location"].id)
    with pytest.raises(LocationNotFoundError):
        c["delete"](c["tenant"], c["location"].id)


def test_deleted_location_retains_event_history_and_replay(context):
    c = context
    t = datetime.now(timezone.utc)
    location_id = c["location"].id
    received = StockReceived(
        id=uuid4(), tenant_id=c["tenant"], article_id=c["article"],
        location_id=location_id, quantity=Decimal("10"), occurred_at=t,
    )
    consumed = StockConsumed(
        id=uuid4(), tenant_id=c["tenant"], article_id=c["article"],
        location_id=location_id, quantity=Decimal("10"), occurred_at=t,
    )
    c["events"].append(received)
    c["events"].append(consumed)
    c["balances"].save(StockBalance(
        tenant_id=c["tenant"], article_id=c["article"],
        location_id=location_id, quantity=Decimal("0"),
    ))

    c["delete"](c["tenant"], location_id)

    history = GetStockHistory(c["events"], c["locations"])(
        c["tenant"], c["article"], location_id
    )
    assert history == [received, consumed]
    assert len(c["events"].list_all_events(c["tenant"])) == 2

    reconstructed = RebuildStockBalances(
        c["events"], StockBalanceProjector()
    )(c["tenant"])
    assert len(reconstructed) == 1
    assert reconstructed[0].location_id == location_id
    assert reconstructed[0].quantity == Decimal("0")


def test_deleted_location_history_not_visible_to_other_tenant(context):
    c = context
    c["delete"](c["tenant"], c["location"].id)

    history = GetStockHistory(c["events"], c["locations"])
    with pytest.raises(LocationNotFoundError):
        history(c["foreign_tenant"], c["article"], c["location"].id)
