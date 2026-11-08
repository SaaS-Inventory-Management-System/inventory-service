from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.usecases.stock_event import (
    ConsumeStock,
    ReceiveStock,
    TransferStock,
)
from app.usecases.stock_balance import RebuildStockBalances
from app.usecases.projections import StockBalanceProjector
from app.domain.entities import Location, StockBalance
from app.domain.errors import InsufficientStockError
from app.domain.events import StockConsumed, StockReceived
from app.fakes.repositories import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository,
)


@pytest.fixture
def context():
    tenant, another_tenant = uuid4(), uuid4()
    article, other_article = uuid4(), uuid4()
    source, destination, third = uuid4(), uuid4(), uuid4()
    locations = InMemoryLocationRepository()
    for ident, name in (
        (source, "Skladisce"),
        (destination, "Delavnica"),
        (third, "Kombi"),
    ):
        locations.save(Location(id=ident, tenant_id=tenant, name=name))

    events = InMemoryStockEventRepository()
    balances = InMemoryStockBalanceRepository()
    projector = StockBalanceProjector()
    dependencies = dict(
        location_repository=locations,
        event_repository=events,
        balance_repository=balances,
        projector=projector,
    )
    return {
        "tenant": tenant, "another_tenant": another_tenant,
        "article": article, "other_article": other_article,
        "source": source, "destination": destination, "third": third,
        "events": events, "balances": balances,
        "receive": ReceiveStock(**dependencies),
        "consume": ConsumeStock(**dependencies),
        "transfer": TransferStock(**dependencies),
        "rebuild": RebuildStockBalances(
            event_repository=events, projector=projector,
        ),
    }


def as_map(stock_balances):
    return {
        (b.tenant_id, b.article_id, b.location_id): b.quantity
        for b in stock_balances
    }


def test_replay_without_events_is_empty(context):
    c = context
    assert c["rebuild"](c["tenant"]) == []


def test_replay_received_consumed_and_transfer_with_new_destination(context):
    c = context
    t, a, source, destination = (
        c["tenant"], c["article"], c["source"], c["destination"]
    )
    c["receive"](t, a, source, Decimal("100"))
    c["consume"](t, a, source, Decimal("10"), reason="Poraba")
    c["transfer"](t, a, source, destination, Decimal("25"))
    c["consume"](t, a, destination, Decimal("5"))

    rebuilt = as_map(c["rebuild"](t))
    assert rebuilt == {
        (t, a, source): Decimal("65"),
        (t, a, destination): Decimal("20"),
    }
    assert rebuilt == as_map(c["balances"].list_balances(t))


def test_replay_multiple_articles_and_multiple_transfers(context):
    c = context
    t, article, other = c["tenant"], c["article"], c["other_article"]
    source, destination, third = c["source"], c["destination"], c["third"]
    c["receive"](t, article, source, Decimal("20.5"))
    c["receive"](t, other, source, Decimal("13"))
    c["transfer"](t, article, source, destination, Decimal("4.5"))
    c["transfer"](t, article, destination, third, Decimal("1.5"))
    c["consume"](t, other, source, Decimal("3"))
    assert as_map(c["rebuild"](t)) == {
        (t, article, source): Decimal("16"),
        (t, article, destination): Decimal("3"),
        (t, article, third): Decimal("1.5"),
        (t, other, source): Decimal("10"),
    }


def test_replay_includes_zero_balance_after_full_transfer(context):
    c = context
    t, a, source, destination = (
        c["tenant"], c["article"], c["source"], c["destination"]
    )
    c["receive"](t, a, source, Decimal("7"))
    c["transfer"](t, a, source, destination, Decimal("7"))
    assert as_map(c["rebuild"](t)) == {
        (t, a, source): Decimal("0"),
        (t, a, destination): Decimal("7"),
    }


def test_replay_ignores_foreign_tenant_events(context):
    c = context
    t, foreign, a, source = (
        c["tenant"], c["another_tenant"], c["article"], c["source"]
    )
    time = datetime.now(timezone.utc)
    c["events"].append(StockReceived(
        id=uuid4(), tenant_id=foreign, article_id=a,
        location_id=source, quantity=Decimal("999"), occurred_at=time,
    ))
    c["receive"](t, a, source, Decimal("3"))
    assert as_map(c["rebuild"](t)) == {(t, a, source): Decimal("3")}
    assert as_map(c["rebuild"](foreign)) == {(foreign, a, source): Decimal("999")}


def test_replay_does_not_read_stored_balance_and_can_detect_corruption(context):
    c = context
    t, a, source = c["tenant"], c["article"], c["source"]
    c["receive"](t, a, source, Decimal("12"))
    corrupted = StockBalance(
        tenant_id=t, article_id=a, location_id=source, quantity=Decimal("999"),
    )
    c["balances"].save(corrupted)

    assert as_map(c["rebuild"](t)) == {(t, a, source): Decimal("12")}
    assert c["balances"].get_by_ids(t, a, source) == corrupted


def test_replay_is_deterministic_and_does_not_modify_events_or_balances(context):
    c = context
    t, a, source, destination = (
        c["tenant"], c["article"], c["source"], c["destination"]
    )
    c["receive"](t, a, source, Decimal("9"))
    c["transfer"](t, a, source, destination, Decimal("4"))
    events_before = c["events"].list_all_events(t)
    balances_before = as_map(c["balances"].list_balances(t))

    first = as_map(c["rebuild"](t))
    second = as_map(c["rebuild"](t))

    assert first == second == balances_before
    assert c["events"].list_all_events(t) == events_before
    assert as_map(c["balances"].list_balances(t)) == balances_before


def test_replay_invalid_event_order_raises_instead_of_hiding_error(context):
    c = context
    t, a, source = c["tenant"], c["article"], c["source"]
    time = datetime.now(timezone.utc)
    consumed = StockConsumed(
        id=uuid4(), tenant_id=t, article_id=a,
        location_id=source, quantity=Decimal("2"), occurred_at=time,
    )
    received = StockReceived(
        id=uuid4(), tenant_id=t, article_id=a,
        location_id=source, quantity=Decimal("10"), occurred_at=time,
    )
    c["events"].append(consumed)
    c["events"].append(received)

    with pytest.raises(InsufficientStockError):
        c["rebuild"](t)


def test_replay_unknown_event_type_raises_type_error():
    class UnknownEventRepository:
        def list_all_events(self, tenant_id):
            return [object()]

    replay = RebuildStockBalances(
        event_repository=UnknownEventRepository(),
        projector=StockBalanceProjector(),
    )
    with pytest.raises(TypeError, match="Unsupported stock event type"):
        replay(uuid4())
