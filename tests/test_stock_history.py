from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.usecases.stock_balance import GetStockHistory
from app.domain.entities import Location
from app.domain.errors import LocationNotFoundError
from app.domain.events import StockConsumed
from app.domain.events import StockReceived
from app.domain.events import StockTransferred
from app.fakes.repositories import (
    InMemoryLocationRepository,
    InMemoryStockEventRepository,
)

@pytest.fixture
def context():
    tenant, other_tenant = uuid4(), uuid4()
    article, another_article = uuid4(), uuid4()
    source, destination, foreign_location = uuid4(), uuid4(), uuid4()

    locations = InMemoryLocationRepository()
    locations.save(Location(id=source, tenant_id=tenant, name="Glavno skladišče"))
    locations.save(Location(id=destination, tenant_id=tenant, name="Delavnica"))
    locations.save(Location(id=foreign_location, tenant_id=other_tenant, name="Tuja lokacija"))

    events = InMemoryStockEventRepository()
    return {
        "tenant": tenant,
        "other_tenant": other_tenant,
        "article": article,
        "another_article": another_article,
        "source": source,
        "destination": destination,
        "foreign_location": foreign_location,
        "events": events,
        "history": GetStockHistory(
            event_repository=events,
            location_repository=locations,
        ),
    }


def test_history_returns_empty_list_for_valid_location_without_events(context):
    c = context
    assert c["history"](c["tenant"], c["article"], c["source"]) == []


def test_history_contains_all_types_in_append_order(context):
    c = context
    time = datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc)
    received = StockReceived(
        id=uuid4(), tenant_id=c["tenant"], article_id=c["article"],
        location_id=c["source"], quantity=Decimal("100"), occurred_at=time,
    )
    consumed = StockConsumed(
        id=uuid4(), tenant_id=c["tenant"], article_id=c["article"],
        location_id=c["source"], quantity=Decimal("10"), occurred_at=time,
        reason="Uporaba", reference="DEL-1",
    )
    transferred = StockTransferred(
        id=uuid4(), tenant_id=c["tenant"], article_id=c["article"],
        from_location_id=c["source"], to_location_id=c["destination"],
        quantity=Decimal("25"), occurred_at=time,
        reason="Premik", reference="PRE-1",
    )
    for event in (received, consumed, transferred):
        c["events"].append(event)

    assert c["history"](c["tenant"], c["article"], c["source"]) == [
        received, consumed, transferred,
    ]
    assert c["history"](c["tenant"], c["article"], c["destination"]) == [
        transferred,
    ]


def test_history_scopes_results_by_article_and_tenant(context):
    c = context
    time = datetime.now(timezone.utc)
    own_event = StockReceived(
        id=uuid4(), tenant_id=c["tenant"], article_id=c["article"],
        location_id=c["source"], quantity=Decimal("20"), occurred_at=time,
    )
    different_article = StockReceived(
        id=uuid4(), tenant_id=c["tenant"], article_id=c["another_article"],
        location_id=c["source"], quantity=Decimal("30"), occurred_at=time,
    )
    different_tenant = StockReceived(
        id=uuid4(), tenant_id=c["other_tenant"], article_id=c["article"],
        location_id=c["foreign_location"], quantity=Decimal("99"), occurred_at=time,
    )
    for event in (own_event, different_article, different_tenant):
        c["events"].append(event)

    assert c["history"](c["tenant"], c["article"], c["source"]) == [own_event]
    assert c["history"](c["tenant"], c["another_article"], c["source"]) == [
        different_article,
    ]
    assert c["history"](
        c["other_tenant"], c["article"], c["foreign_location"]
    ) == [different_tenant]


@pytest.mark.parametrize("location_key", ["foreign_location", None])
def test_history_rejects_foreign_or_unknown_location(context, location_key):
    c = context
    location = c[location_key] if location_key else uuid4()
    with pytest.raises(LocationNotFoundError):
        c["history"](c["tenant"], c["article"], location)


def test_history_is_read_only_and_preserves_event_objects(context):
    c = context
    event = StockReceived(
        id=uuid4(), tenant_id=c["tenant"], article_id=c["article"],
        location_id=c["source"], quantity=Decimal("7.5"),
        occurred_at=datetime.now(timezone.utc),
    )
    c["events"].append(event)

    first = c["history"](c["tenant"], c["article"], c["source"])
    second = c["history"](c["tenant"], c["article"], c["source"])
    assert first == second == [event]
    assert first[0] is event
    assert c["events"].list_events(c["tenant"], c["article"], c["source"]) == [event]
