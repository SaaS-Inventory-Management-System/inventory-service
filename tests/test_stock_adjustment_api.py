from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.projections import StockBalanceProjector
from app.domain.entities import Location
from app.infrastructure.repositories.in_memory import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository,
)
from app.presentation.routers.stocks import create_router


@pytest.fixture
def api_context():
    tenant = UUID("11111111-1111-4111-8111-111111111111")
    foreign_tenant = uuid4()
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
    app = FastAPI()
    app.include_router(create_router(
        location_repository=locations,
        event_repository=events,
        balance_repository=balances,
        projector=StockBalanceProjector(),
    ))
    return {
        "client": TestClient(app), "tenant": tenant,
        "article": article, "other_article": other_article,
        "source": source, "destination": destination,
        "foreign_location": foreign_location,
        "events": events, "balances": balances,
    }


def adjust(client, article, location, quantity, **extra):
    payload = {
        "article_id": str(article),
        "location_id": str(location),
        "counted_quantity": str(quantity),
        "reason": "Physical inventory count",
    }
    payload.update(extra)
    return client.post("/stock/adjust", json=payload)


def receive(client, article, location, quantity):
    response = client.post("/stock/receive", json={
        "article_id": str(article),
        "location_id": str(location),
        "quantity": str(quantity),
    })
    assert response.status_code == 200, response.text


def transfer(client, article, source, destination, quantity):
    response = client.post("/stock/transfer", json={
        "article_id": str(article),
        "from_location_id": str(source),
        "to_location_id": str(destination),
        "quantity": str(quantity),
    })
    assert response.status_code == 200, response.text


def stock_map(rows):
    return {
        (row["article_id"], row["location_id"]): Decimal(str(row["quantity"]))
        for row in rows
    }


def test_adjust_endpoint_returns_updated_balance_with_200(api_context):
    c = api_context
    receive(c["client"], c["article"], c["source"], "100")

    response = adjust(c["client"], c["article"], c["source"], "92.5")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["tenant_id"] == str(c["tenant"])
    assert data["article_id"] == str(c["article"])
    assert data["location_id"] == str(c["source"])
    assert Decimal(str(data["quantity"])) == Decimal("92.5")
    current = c["client"].get(
        f"/stock/balances/{c['source']}/{c['article']}"
    )
    assert current.status_code == 200
    assert Decimal(str(current.json()["quantity"])) == Decimal("92.5")


@pytest.mark.parametrize("quantity", ["0", "7.5"])
def test_adjust_endpoint_creates_balance_for_new_article(api_context, quantity):
    c = api_context
    response = adjust(c["client"], c["article"], c["source"], quantity)
    assert response.status_code == 200, response.text
    assert Decimal(str(response.json()["quantity"])) == Decimal(quantity)
    assert len(c["events"].list_all_events(c["tenant"])) == 1


@pytest.mark.parametrize("quantity", ["-1", "-0.1", "NaN", "Infinity"])
def test_adjust_endpoint_rejects_invalid_counted_quantity_without_writes(
    api_context, quantity
):
    c = api_context
    response = adjust(c["client"], c["article"], c["source"], quantity)
    assert response.status_code == 422, response.text
    assert c["events"].list_all_events(c["tenant"]) == []
    assert c["balances"].list_balances(c["tenant"]) == []


@pytest.mark.parametrize("reason", ["", "   "])
def test_adjust_endpoint_rejects_blank_reason(api_context, reason):
    c = api_context
    response = adjust(
        c["client"], c["article"], c["source"], "10", reason=reason
    )
    assert response.status_code == 422, response.text
    assert c["events"].list_all_events(c["tenant"]) == []


@pytest.mark.parametrize("location_mode", ["unknown", "foreign"])
def test_adjust_endpoint_rejects_missing_or_foreign_location(api_context, location_mode):
    c = api_context
    location = uuid4() if location_mode == "unknown" else c["foreign_location"]
    response = adjust(c["client"], c["article"], location, "3")
    assert response.status_code == 404, response.text
    assert c["events"].list_all_events(c["tenant"]) == []


@pytest.mark.parametrize("invalid_field", ["article_id", "location_id", "counted_quantity", "reason"])
def test_adjust_endpoint_validates_required_fields_and_uuid(api_context, invalid_field):
    c = api_context
    payload = {
        "article_id": str(c["article"]),
        "location_id": str(c["source"]),
        "counted_quantity": "5",
        "reason": "Count",
    }
    if invalid_field in ("article_id", "location_id"):
        payload[invalid_field] = "not-a-uuid"
    else:
        del payload[invalid_field]

    response = c["client"].post("/stock/adjust", json=payload)
    assert response.status_code == 422, response.text
    assert c["events"].list_all_events(c["tenant"]) == []


def test_adjustment_appears_in_history_with_discriminator_and_metadata(api_context):
    c = api_context
    response = adjust(
        c["client"], c["article"], c["source"], "12.75",
        reason="Recount", reference="INV-77",
    )
    assert response.status_code == 200, response.text

    history_response = c["client"].get(
        f"/stock/history/{c['source']}/{c['article']}"
    )
    assert history_response.status_code == 200, history_response.text
    events = history_response.json()
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "adjusted"
    assert event["tenant_id"] == str(c["tenant"])
    assert event["article_id"] == str(c["article"])
    assert event["location_id"] == str(c["source"])
    assert Decimal(str(event["counted_quantity"])) == Decimal("12.75")
    assert event["reason"] == "Recount"
    assert event["reference"] == "INV-77"
    assert UUID(event["id"])
    assert event["occurred_at"]
    assert "quantity" not in event  # inventura ima counted_quantity


def test_history_and_replay_support_adjustment_among_other_event_types(api_context):
    c = api_context
    client, article = c["client"], c["article"]
    source, destination = c["source"], c["destination"]
    receive(client, article, source, "100")
    transfer(client, article, source, destination, "20")
    response = adjust(client, article, source, "75", reason="Recount")
    assert response.status_code == 200, response.text
    response = adjust(client, article, destination, "0", reason="Missing material")
    assert response.status_code == 200, response.text

    source_history = client.get(f"/stock/history/{source}/{article}")
    destination_history = client.get(f"/stock/history/{destination}/{article}")
    assert source_history.status_code == destination_history.status_code == 200
    assert [e["event_type"] for e in source_history.json()] == [
        "received", "transferred", "adjusted"
    ]
    assert [e["event_type"] for e in destination_history.json()] == [
        "transferred", "adjusted"
    ]

    current = client.get("/stock/balances")
    preview = client.post("/stock/replay/preview")
    assert current.status_code == preview.status_code == 200
    expected = {
        (str(article), str(source)): Decimal("75"),
        (str(article), str(destination)): Decimal("0"),
    }
    assert stock_map(current.json()) == expected
    assert stock_map(preview.json()) == expected
    # Preview ni zapisovalna operacija: stevilo dogodkov ostane enako.
    assert len(c["events"].list_all_events(c["tenant"])) == 4


def test_adjustment_history_is_filtered_by_article_and_location(api_context):
    c = api_context
    client = c["client"]
    assert adjust(client, c["article"], c["source"], "3").status_code == 200
    assert adjust(client, c["other_article"], c["source"], "4").status_code == 200
    assert adjust(client, c["article"], c["destination"], "5").status_code == 200
    result = client.get(f"/stock/history/{c['source']}/{c['article']}")
    assert result.status_code == 200, result.text
    assert len(result.json()) == 1
    assert Decimal(str(result.json()[0]["counted_quantity"])) == Decimal("3")
