from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.domain.events import StockConsumed, StockReceived, StockTransferred
from app.infrastructure.repositories.in_memory import (
    InMemoryStockEventRepository,
)


def test_list_all_events_returns_each_event_once_in_append_order():
    tenant, article, source, destination = uuid4(), uuid4(), uuid4(), uuid4()
    another_tenant = uuid4()
    t = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    store = InMemoryStockEventRepository()

    received = StockReceived(
        id=uuid4(), tenant_id=tenant, article_id=article,
        location_id=source, quantity=Decimal("100"), occurred_at=t,
    )
    transferred = StockTransferred(
        id=uuid4(), tenant_id=tenant, article_id=article,
        from_location_id=source, to_location_id=destination,
        quantity=Decimal("20"), occurred_at=t - timedelta(hours=1),
    )
    foreign = StockReceived(
        id=uuid4(), tenant_id=another_tenant, article_id=article,
        location_id=source, quantity=Decimal("999"), occurred_at=t,
    )
    consumed = StockConsumed(
        id=uuid4(), tenant_id=tenant, article_id=article,
        location_id=destination, quantity=Decimal("5"), occurred_at=t,
    )
    for event in (received, transferred, foreign, consumed):
        store.append(event)

    assert store.list_all_events(tenant) == [received, transferred, consumed]
    assert store.list_all_events(another_tenant) == [foreign]
    assert sum(isinstance(e, StockTransferred) for e in store.list_all_events(tenant)) == 1


def test_list_all_events_returns_empty_list_for_unknown_tenant():
    store = InMemoryStockEventRepository()
    store.append(StockReceived(
        id=uuid4(), tenant_id=uuid4(), article_id=uuid4(),
        location_id=uuid4(), quantity=Decimal("1"),
        occurred_at=datetime.now(timezone.utc),
    ))
    assert store.list_all_events(uuid4()) == []


def test_mutating_returned_event_list_does_not_change_store():
    tenant = uuid4()
    store = InMemoryStockEventRepository()
    event = StockReceived(
        id=uuid4(), tenant_id=tenant, article_id=uuid4(),
        location_id=uuid4(), quantity=Decimal("4"),
        occurred_at=datetime.now(timezone.utc),
    )
    store.append(event)
    results = store.list_all_events(tenant)
    results.clear()
    assert store.list_all_events(tenant) == [event]
