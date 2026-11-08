from decimal import Decimal
from uuid import uuid4

import pytest

from app.usecases.stock_event import (
    AdjustStock,
    ConsumeStock,
    ReceiveStock,
    TransferStock,
)
from app.usecases.stock_balance import (
    GetStockHistory,
    RebuildStockBalances,
)
from app.usecases.projections import StockBalanceProjector
from app.domain.entities import Location
from app.domain.errors import LocationNotFoundError
from app.domain.events import StockAdjusted
from app.fakes.repositories import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository,
)


@pytest.fixture
def stock_context():
    tenant, foreign_tenant = uuid4(), uuid4()
    article, other_article = uuid4(), uuid4()
    source, destination, foreign_location = uuid4(), uuid4(), uuid4()

    locations = InMemoryLocationRepository()
    locations.save(Location(id=source, tenant_id=tenant, name="Skladisce"))
    locations.save(Location(id=destination, tenant_id=tenant, name="Delavnica"))
    locations.save(Location(
        id=foreign_location, tenant_id=foreign_tenant, name="Tuja lokacija"
    ))
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
        "tenant": tenant,
        "foreign_tenant": foreign_tenant,
        "article": article,
        "other_article": other_article,
        "source": source,
        "destination": destination,
        "foreign_location": foreign_location,
        "events": events,
        "balances": balances,
        "adjust": AdjustStock(**dependencies),
        "receive": ReceiveStock(**dependencies),
        "consume": ConsumeStock(**dependencies),
        "transfer": TransferStock(**dependencies),
        "history": GetStockHistory(
            event_repository=events, location_repository=locations
        ),
        "rebuild": RebuildStockBalances(
            event_repository=events, projector=projector
        ),
    }


def get_balance(c, location=None, article=None):
    return c["balances"].get_by_ids(
        c["tenant"],
        article if article is not None else c["article"],
        location if location is not None else c["source"],
    )


def get_events(c, location=None, article=None):
    return c["events"].list_events(
        c["tenant"],
        article if article is not None else c["article"],
        location if location is not None else c["source"],
    )


def balance_map(items):
    return {
        (item.tenant_id, item.article_id, item.location_id): item.quantity
        for item in items
    }


def test_adjust_existing_balance_records_absolute_count_and_one_event(stock_context):
    c = stock_context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("100"))

    adjusted = c["adjust"](
        c["tenant"], c["article"], c["source"], Decimal("92"),
        reason="Physical inventory count", reference="INV-12",
    )

    assert adjusted.quantity == Decimal("92")
    assert get_balance(c) == adjusted
    history = get_events(c)
    assert len(history) == 2
    event = history[-1]
    assert isinstance(event, StockAdjusted)
    assert event.counted_quantity == Decimal("92")
    assert event.reason == "Physical inventory count"
    assert event.reference == "INV-12"
    assert c["events"].list_all_events(c["tenant"]).count(event) == 1


@pytest.mark.parametrize("quantity", ["0", "12.5"])
def test_adjust_can_initialize_missing_stock_balance(stock_context, quantity):
    c = stock_context
    assert get_balance(c) is None

    result = c["adjust"](
        c["tenant"], c["article"], c["source"],
        Decimal(quantity), reason="Initial physical count",
    )

    assert result.quantity == Decimal(quantity)
    assert get_balance(c) == result
    assert len(get_events(c)) == 1
    assert isinstance(get_events(c)[0], StockAdjusted)
    assert get_events(c)[0].reference is None
    assert balance_map(c["rebuild"](c["tenant"])) == {
        (c["tenant"], c["article"], c["source"]): Decimal(quantity)
    }


def test_adjustments_overwrite_instead_of_accumulating(stock_context):
    c = stock_context
    t, a, loc = c["tenant"], c["article"], c["source"]
    c["receive"](t, a, loc, Decimal("20"))
    c["adjust"](t, a, loc, Decimal("17"), reason="First count")
    c["adjust"](t, a, loc, Decimal("19"), reason="Recount")
    c["consume"](t, a, loc, Decimal("4"), reason="Used")

    assert get_balance(c).quantity == Decimal("15")
    assert [type(event).__name__ for event in get_events(c)] == [
        "StockReceived", "StockAdjusted", "StockAdjusted", "StockConsumed"
    ]
    assert balance_map(c["rebuild"](t)) == {
        (t, a, loc): Decimal("15")
    }


@pytest.mark.parametrize("quantity", ["-1", "NaN", "Infinity", "-Infinity"])
def test_invalid_adjustment_does_not_change_state_or_append_event(
    stock_context, quantity
):
    c = stock_context
    t, a, loc = c["tenant"], c["article"], c["source"]
    c["receive"](t, a, loc, Decimal("11"))
    original_balance = get_balance(c)
    original_events = c["events"].list_all_events(t)

    with pytest.raises(ValueError):
        c["adjust"](t, a, loc, Decimal(quantity), reason="Count")

    assert get_balance(c) == original_balance
    assert c["events"].list_all_events(t) == original_events


@pytest.mark.parametrize("reason", ["", "   "])
def test_blank_reason_does_not_change_stock(stock_context, reason):
    c = stock_context
    with pytest.raises(ValueError):
        c["adjust"](
            c["tenant"], c["article"], c["source"],
            Decimal("5"), reason=reason,
        )
    assert get_balance(c) is None
    assert get_events(c) == []


@pytest.mark.parametrize("location_type", ["unknown", "foreign"])
def test_adjust_rejects_unknown_or_other_tenants_location(stock_context, location_type):
    c = stock_context
    location = uuid4() if location_type == "unknown" else c["foreign_location"]
    with pytest.raises(LocationNotFoundError):
        c["adjust"](
            c["tenant"], c["article"], location,
            Decimal("9"), reason="Count",
        )
    assert get_balance(c) is None
    assert c["events"].list_all_events(c["tenant"]) == []


def test_history_and_event_store_filter_adjustments_by_article_location_and_tenant(
    stock_context,
):
    c = stock_context
    t, a, loc = c["tenant"], c["article"], c["source"]
    c["adjust"](t, a, loc, Decimal("3"), reason="Article A")
    c["adjust"](t, c["other_article"], loc, Decimal("7"), reason="Article B")
    c["adjust"](t, a, c["destination"], Decimal("9"), reason="Other location")

    history = c["history"](t, a, loc)
    assert len(history) == 1
    assert isinstance(history[0], StockAdjusted)
    assert history[0].reason == "Article A"
    assert len(c["events"].list_all_events(t)) == 3
    assert c["history"](t, a, c["destination"])[0].reason == "Other location"
    assert c["events"].list_all_events(c["foreign_tenant"]) == []


def test_replay_after_adjustment_and_transfer_matches_stored_balances(stock_context):
    c = stock_context
    t, a, source, destination = (
        c["tenant"], c["article"], c["source"], c["destination"]
    )
    c["receive"](t, a, source, Decimal("100"))
    c["transfer"](t, a, source, destination, Decimal("30"))
    c["adjust"](t, a, source, Decimal("65"), reason="Count in warehouse")
    c["adjust"](t, a, destination, Decimal("35"), reason="Count in workshop")
    c["consume"](t, a, destination, Decimal("5"), reason="Production")
    c["adjust"](t, c["other_article"], source, Decimal("2"), reason="Initial count")

    expected = {
        (t, a, source): Decimal("65"),
        (t, a, destination): Decimal("30"),
        (t, c["other_article"], source): Decimal("2"),
    }
    assert balance_map(c["rebuild"](t)) == expected
    assert balance_map(c["balances"].list_balances(t)) == expected


def test_replay_ignores_corrupt_read_model_and_does_not_repair_it(stock_context):
    c = stock_context
    t, a, loc = c["tenant"], c["article"], c["source"]
    c["adjust"](t, a, loc, Decimal("6"), reason="Count")

    from app.domain.entities import StockBalance

    incorrect = StockBalance(t, a, loc, Decimal("999"))
    c["balances"].save(incorrect)

    assert balance_map(c["rebuild"](t)) == {(t, a, loc): Decimal("6")}
    assert get_balance(c) == incorrect  # preview does not modify stored balances
