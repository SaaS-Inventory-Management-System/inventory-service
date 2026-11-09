from datetime import datetime
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
def stock_client():
    tenant = UUID("11111111-1111-4111-8111-111111111111")
    other_tenant = uuid4()
    article, other_article = uuid4(), uuid4()
    source, destination, empty_location, foreign_location = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    locations = InMemoryLocationRepository()
    for ident, tenant_id, name in (
        (source, tenant, "Skladišče"),
        (destination, tenant, "Delavnica"),
        (empty_location, tenant, "Prazna lokacija"),
        (foreign_location, other_tenant, "Tuje skladišče"),
    ):
        locations.save(Location(id=ident, tenant_id=tenant_id, name=name))

    app = FastAPI()
    app.include_router(create_router(
        location_repository=locations,
        event_repository=InMemoryStockEventRepository(),
        balance_repository=InMemoryStockBalanceRepository(),
        projector=StockBalanceProjector(),
    ))
    return {
        "client": TestClient(app),
        "tenant": tenant,
        "article": article,
        "other_article": other_article,
        "source": source,
        "destination": destination,
        "empty": empty_location,
        "foreign": foreign_location,
    }


def history(client, location_id, article_id):
    return client.get(f"/stock/history/{location_id}/{article_id}")


def receive(client, article, location, quantity):
    response = client.post("/stock/receive", json={
        "article_id": str(article), "location_id": str(location),
        "quantity": str(quantity),
    })
    assert response.status_code == 200, response.text


def consume(client, article, location, quantity, **extra):
    response = client.post("/stock/consume", json={
        "article_id": str(article), "location_id": str(location),
        "quantity": str(quantity), **extra,
    })
    assert response.status_code == 200, response.text


def transfer(client, article, source, destination, quantity, **extra):
    response = client.post("/stock/transfer", json={
        "article_id": str(article), "from_location_id": str(source),
        "to_location_id": str(destination), "quantity": str(quantity), **extra,
    })
    assert response.status_code == 200, response.text


def test_history_received_event_has_expected_response_schema(stock_client):
    c = stock_client
    receive(c["client"], c["article"], c["source"], "12.5")

    response = history(c["client"], c["source"], c["article"])
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data) == 1
    event = data[0]
    assert event["event_type"] == "received"
    assert UUID(event["id"])
    assert event["tenant_id"] == str(c["tenant"])
    assert event["article_id"] == str(c["article"])
    assert event["location_id"] == str(c["source"])
    assert Decimal(str(event["quantity"])) == Decimal("12.5")
    assert datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    assert "from_location_id" not in event
    assert "to_location_id" not in event


def test_history_includes_consumption_and_shared_transfer_in_both_locations(stock_client):
    c = stock_client
    client, article = c["client"], c["article"]
    source, destination = c["source"], c["destination"]
    receive(client, article, source, "100")
    consume(client, article, source, "10", reason="Poraba", reference="DEL-1")
    transfer(client, article, source, destination, "25", reason="Premik", reference="PR-2")
    consume(client, article, destination, "5", reason="Delo")

    source_response = history(client, source, article)
    destination_response = history(client, destination, article)
    assert source_response.status_code == 200, source_response.text
    assert destination_response.status_code == 200, destination_response.text
    source_events = source_response.json()
    destination_events = destination_response.json()

    assert [e["event_type"] for e in source_events] == [
        "received", "consumed", "transferred"
    ]
    assert [e["event_type"] for e in destination_events] == [
        "transferred", "consumed"
    ]
    assert [Decimal(str(e["quantity"])) for e in source_events] == [
        Decimal("100"), Decimal("10"), Decimal("25")
    ]
    assert source_events[1]["reason"] == "Poraba"
    assert source_events[1]["reference"] == "DEL-1"
    assert source_events[2]["reason"] == "Premik"
    assert source_events[2]["reference"] == "PR-2"
    assert source_events[2]["from_location_id"] == str(source)
    assert source_events[2]["to_location_id"] == str(destination)
    assert source_events[2]["id"] == destination_events[0]["id"]
    assert destination_events[1]["location_id"] == str(destination)
    assert destination_events[1]["reason"] == "Delo"
    assert destination_events[1]["reference"] is None

    source_balance = client.get(f"/stock/balances/{source}/{article}")
    destination_balance = client.get(f"/stock/balances/{destination}/{article}")
    assert source_balance.status_code == 200
    assert destination_balance.status_code == 200
    assert Decimal(str(source_balance.json()["quantity"])) == Decimal("65")
    assert Decimal(str(destination_balance.json()["quantity"])) == Decimal("20")


def test_history_filters_by_article_and_returns_empty_for_valid_location(stock_client):
    c = stock_client
    client = c["client"]
    receive(client, c["article"], c["source"], "9")
    receive(client, c["other_article"], c["source"], "4")

    source = history(client, c["source"], c["article"])
    other_article = history(client, c["source"], c["other_article"])
    empty = history(client, c["empty"], c["article"])
    assert source.status_code == other_article.status_code == empty.status_code == 200
    assert len(source.json()) == len(other_article.json()) == 1
    assert source.json()[0]["article_id"] == str(c["article"])
    assert other_article.json()[0]["article_id"] == str(c["other_article"])
    assert empty.json() == []


def test_history_is_read_only(stock_client):
    c = stock_client
    client = c["client"]
    receive(client, c["article"], c["source"], "8")
    balance_before = client.get(f"/stock/balances/{c['source']}/{c['article']}").json()
    first = history(client, c["source"], c["article"])
    second = history(client, c["source"], c["article"])
    balance_after = client.get(f"/stock/balances/{c['source']}/{c['article']}").json()

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert balance_before == balance_after


@pytest.mark.parametrize("location_mode", ["missing", "foreign"])
def test_history_returns_404_for_unknown_or_other_tenants_location(stock_client, location_mode):
    c = stock_client
    location_id = uuid4() if location_mode == "missing" else c["foreign"]
    response = history(c["client"], location_id, c["article"])
    assert response.status_code == 404


@pytest.mark.parametrize("bad_part", ["location", "article"])
def test_history_returns_422_for_invalid_uuid(stock_client, bad_part):
    c = stock_client
    location_id = "not-a-uuid" if bad_part == "location" else str(c["source"])
    article_id = "not-a-uuid" if bad_part == "article" else str(c["article"])
    response = history(c["client"], location_id, article_id)
    assert response.status_code == 422
