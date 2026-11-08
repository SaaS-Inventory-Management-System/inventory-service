"""HTTP tests for reading stock balances through the stock router."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.usecases.projections import StockBalanceProjector
from app.domain.entities import Location
from app.fakes.repositories import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository,
)
from app.presentation.routers.stock import create_router


@pytest.fixture
def stock_client():
    tenant = UUID("11111111-1111-4111-8111-111111111111")
    location_a, location_b = uuid4(), uuid4()
    article_a, article_b = uuid4(), uuid4()
    locations = InMemoryLocationRepository()
    locations.save(Location(id=location_a, tenant_id=tenant, name="Skladišče"))
    locations.save(Location(id=location_b, tenant_id=tenant, name="Delavnica"))

    app = FastAPI()
    app.include_router(create_router(
        location_repository=locations,
        event_repository=InMemoryStockEventRepository(),
        balance_repository=InMemoryStockBalanceRepository(),
        projector=StockBalanceProjector(),
    ))
    client = TestClient(app)

    def receive(article, location, amount):
        response = client.post("/stock/receive", json={
            "article_id": str(article),
            "location_id": str(location),
            "quantity": str(amount),
        })
        assert response.status_code == 200, response.text

    receive(article_a, location_a, "50")
    receive(article_b, location_a, "12.5")
    receive(article_a, location_b, "7")
    return client, article_a, article_b, location_a, location_b


def test_get_one_balance_returns_quantity(stock_client):
    client, article_a, _, location_a, _ = stock_client
    response = client.get(f"/stock/balances/{location_a}/{article_a}")

    assert response.status_code == 200
    assert Decimal(response.json()["quantity"]) == Decimal("50")
    assert response.json()["article_id"] == str(article_a)
    assert response.json()["location_id"] == str(location_a)


def test_get_unknown_article_returns_zero_for_existing_location(stock_client):
    client, _, _, location_a, _ = stock_client
    unknown_article = uuid4()
    response = client.get(f"/stock/balances/{location_a}/{unknown_article}")

    assert response.status_code == 200
    assert Decimal(response.json()["quantity"]) == Decimal("0")
    assert len(client.get("/stock/balances").json()) == 3


def test_get_one_balance_rejects_missing_location(stock_client):
    client, article_a, _, _, _ = stock_client
    response = client.get(f"/stock/balances/{uuid4()}/{article_a}")
    assert response.status_code == 404


def test_get_one_balance_rejects_invalid_uuid(stock_client):
    client, article_a, _, _, _ = stock_client
    response = client.get(f"/stock/balances/not-a-uuid/{article_a}")
    assert response.status_code == 422


def test_list_all_balances(stock_client):
    client, _, _, _, _ = stock_client
    response = client.get("/stock/balances")

    assert response.status_code == 200
    assert len(response.json()) == 3
    assert {Decimal(b["quantity"]) for b in response.json()} == {
        Decimal("50"), Decimal("12.5"), Decimal("7")
    }


def test_list_balances_filtered_by_location(stock_client):
    client, _, _, location_a, _ = stock_client
    response = client.get("/stock/balances", params={"location_id": str(location_a)})

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert all(b["location_id"] == str(location_a) for b in response.json())


def test_list_balances_missing_location_returns_404(stock_client):
    client, _, _, _, _ = stock_client
    response = client.get("/stock/balances", params={"location_id": str(uuid4())})
    assert response.status_code == 404


def test_list_balances_invalid_uuid_returns_422(stock_client):
    client, _, _, _, _ = stock_client
    response = client.get("/stock/balances", params={"location_id": "not-a-uuid"})
    assert response.status_code == 422
