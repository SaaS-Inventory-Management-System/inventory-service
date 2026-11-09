"""Use-case and event-store tests for transferring stock between locations."""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.usecases.stock_events import ReceiveStock, TransferStock
from app.application.projections import StockBalanceProjector
from app.domain.entities import Location
from app.domain.errors import InsufficientStockError, LocationNotFoundError
from app.domain.events import StockTransferred
from app.infrastructure.repositories.in_memory import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository,
)


@pytest.fixture
def context():
    tenant, other_tenant = uuid4(), uuid4()
    article, source, destination, foreign = uuid4(), uuid4(), uuid4(), uuid4()
    locations = InMemoryLocationRepository()
    events = InMemoryStockEventRepository()
    balances = InMemoryStockBalanceRepository()
    locations.save(Location(id=source, tenant_id=tenant, name="Skladišče"))
    locations.save(Location(id=destination, tenant_id=tenant, name="Delavnica"))
    locations.save(Location(id=foreign, tenant_id=other_tenant, name="Tuja lokacija"))

    dependencies = dict(
        location_repository=locations,
        event_repository=events,
        balance_repository=balances,
        projector=StockBalanceProjector(),
    )
    return {
        "tenant": tenant,
        "other_tenant": other_tenant,
        "article": article,
        "source": source,
        "destination": destination,
        "foreign": foreign,
        "events": events,
        "balances": balances,
        "receive": ReceiveStock(**dependencies),
        "transfer": TransferStock(**dependencies),
    }


def get_balance(context, location):
    return context["balances"].get_by_ids(
        context["tenant"], context["article"], location
    )


def get_events(context, location):
    return context["events"].list_events(
        context["tenant"], context["article"], location
    )


def test_transfer_updates_existing_balances_and_records_one_shared_event(context):
    c = context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("100"))
    c["receive"](c["tenant"], c["article"], c["destination"], Decimal("10"))

    new_source, new_destination = c["transfer"](
        c["tenant"], c["article"], c["source"], c["destination"],
        Decimal("25"), reason="Premik v delavnico", reference="PR-123"
    )

    assert new_source.quantity == Decimal("75")
    assert new_destination.quantity == Decimal("35")
    assert get_balance(c, c["source"]) == new_source
    assert get_balance(c, c["destination"]) == new_destination
    assert new_source.quantity + new_destination.quantity == Decimal("110")

    source_history = get_events(c, c["source"])
    destination_history = get_events(c, c["destination"])
    assert len(source_history) == 2
    assert len(destination_history) == 2
    transfer_from_source = source_history[-1]
    transfer_from_destination = destination_history[-1]
    assert isinstance(transfer_from_source, StockTransferred)
    assert transfer_from_source is transfer_from_destination
    assert transfer_from_source.quantity == Decimal("25")
    assert transfer_from_source.reason == "Premik v delavnico"
    assert transfer_from_source.reference == "PR-123"
    assert transfer_from_source.from_location_id == c["source"]
    assert transfer_from_source.to_location_id == c["destination"]


def test_transfer_creates_destination_balance_if_it_did_not_exist(context):
    c = context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("20"))
    assert get_balance(c, c["destination"]) is None

    source, destination = c["transfer"](
        c["tenant"], c["article"], c["source"], c["destination"],
        Decimal("5")
    )

    assert source.quantity == Decimal("15")
    assert destination.quantity == Decimal("5")
    assert get_balance(c, c["destination"]) == destination
    event = get_events(c, c["destination"])[0]
    assert isinstance(event, StockTransferred)
    assert event.reason is None
    assert event.reference is None


def test_transfer_of_exact_available_amount_leaves_zero_in_source(context):
    c = context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("7"))
    from_balance, to_balance = c["transfer"](
        c["tenant"], c["article"], c["source"], c["destination"],
        Decimal("7")
    )
    assert from_balance.quantity == Decimal("0")
    assert to_balance.quantity == Decimal("7")


def test_transfer_without_source_stock_does_not_write_anything(context):
    c = context
    with pytest.raises(InsufficientStockError):
        c["transfer"](
            c["tenant"], c["article"], c["source"], c["destination"],
            Decimal("1")
        )
    assert get_events(c, c["source"]) == []
    assert get_events(c, c["destination"]) == []
    assert get_balance(c, c["source"]) is None
    assert get_balance(c, c["destination"]) is None


def test_transfer_with_insufficient_stock_keeps_balances_and_histories(context):
    c = context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("8"))
    c["receive"](c["tenant"], c["article"], c["destination"], Decimal("3"))

    with pytest.raises(InsufficientStockError):
        c["transfer"](
            c["tenant"], c["article"], c["source"], c["destination"],
            Decimal("9")
        )

    assert get_balance(c, c["source"]).quantity == Decimal("8")
    assert get_balance(c, c["destination"]).quantity == Decimal("3")
    assert len(get_events(c, c["source"])) == 1
    assert len(get_events(c, c["destination"])) == 1


@pytest.mark.parametrize("missing_side", ["source", "destination"])
def test_transfer_rejects_missing_location_without_changes(context, missing_side):
    c = context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("10"))
    source = uuid4() if missing_side == "source" else c["source"]
    destination = uuid4() if missing_side == "destination" else c["destination"]

    with pytest.raises(LocationNotFoundError):
        c["transfer"](
            c["tenant"], c["article"], source, destination, Decimal("1")
        )

    assert get_balance(c, c["source"]).quantity == Decimal("10")
    assert get_balance(c, c["destination"]) is None
    assert len(get_events(c, c["source"])) == 1


@pytest.mark.parametrize("foreign_side", ["source", "destination"])
def test_transfer_rejects_location_owned_by_another_tenant(context, foreign_side):
    c = context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("10"))
    source = c["foreign"] if foreign_side == "source" else c["source"]
    destination = c["foreign"] if foreign_side == "destination" else c["destination"]

    with pytest.raises(LocationNotFoundError):
        c["transfer"](
            c["tenant"], c["article"], source, destination, Decimal("1")
        )

    assert get_balance(c, c["source"]).quantity == Decimal("10")
    assert get_balance(c, c["destination"]) is None
    assert len(get_events(c, c["source"])) == 1


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity"])
def test_transfer_rejects_invalid_quantity_without_writes(context, quantity):
    c = context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("10"))
    with pytest.raises(ValueError):
        c["transfer"](
            c["tenant"], c["article"], c["source"], c["destination"],
            Decimal(quantity)
        )

    assert get_balance(c, c["source"]).quantity == Decimal("10")
    assert get_balance(c, c["destination"]) is None
    assert len(get_events(c, c["source"])) == 1


def test_transfer_rejects_same_source_and_destination_without_writes(context):
    c = context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("10"))
    with pytest.raises(ValueError):
        c["transfer"](
            c["tenant"], c["article"], c["source"], c["source"],
            Decimal("2")
        )
    assert get_balance(c, c["source"]).quantity == Decimal("10")
    assert len(get_events(c, c["source"])) == 1


def test_transfer_rejects_blank_reason_without_writes(context):
    c = context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("10"))
    with pytest.raises(ValueError):
        c["transfer"](
            c["tenant"], c["article"], c["source"], c["destination"],
            Decimal("2"), reason="   "
        )
    assert get_balance(c, c["source"]).quantity == Decimal("10")
    assert len(get_events(c, c["source"])) == 1


def test_event_store_rejects_duplicate_id_and_preserves_history(context):
    c = context
    c["receive"](c["tenant"], c["article"], c["source"], Decimal("10"))
    c["transfer"](
        c["tenant"], c["article"], c["source"], c["destination"],
        Decimal("2")
    )
    transfer_event = get_events(c, c["destination"])[0]

    with pytest.raises(ValueError):
        c["events"].append(transfer_event)

    assert len(get_events(c, c["source"])) == 2
    assert len(get_events(c, c["destination"])) == 1
