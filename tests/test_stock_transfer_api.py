"""HTTP tests for POST /stock/transfer using the existing stock router."""

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
    # Matches DEV_TENANT_ID currently used by the stock router.
    tenant = UUID("11111111-1111-4111-8111-111111111111")
    other_tenant = uuid4()
    article, source, destination, foreign = uuid4(), uuid4(), uuid4(), uuid4()
    locations = InMemoryLocationRepository()
    locations.save(Location(id=source, tenant_id=tenant, name="Skladišče"))
    locations.save(Location(id=destination, tenant_id=tenant, name="Delavnica"))
    locations.save(Location(id=foreign, tenant_id=other_tenant, name="Tuja lokacija"))

    app = FastAPI()
    app.include_router(create_router(
        location_repository=locations,
        event_repository=InMemoryStockEventRepository(),
        balance_repository=InMemoryStockBalanceRepository(),
        projector=StockBalanceProjector(),
    ))
    return TestClient(app), article, source, destination, foreign


def transfer_payload(article, source, destination, quantity, **extra):
    return {
        "article_id": str(article),
        "from_location_id": str(source),
        "to_location_id": str(destination),
        "quantity": quantity,
        **extra,
    }


def receive(client, article, location, quantity):
    response = client.post("/stock/receive", json={
        "article_id": str(article),
        "location_id": str(location),
        "quantity": quantity,
    })
    assert response.status_code == 200, response.text


def stock_quantity(client, article, location):
    response = client.get(f"/stock/balances/{location}/{article}")
    assert response.status_code == 200, response.text
    return Decimal(str(response.json()["quantity"]))


def test_transfer_endpoint_returns_two_updated_balances(stock_client):
    client, article, source, destination, _ = stock_client
    receive(client, article, source, "100")
    receive(client, article, destination, "10")

    response = client.post("/stock/transfer", json=transfer_payload(
        article, source, destination, "25.5", reason="Delo", reference="PR-1"
    ))

    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(str(body["from_balance"]["quantity"])) == Decimal("74.5")
    assert Decimal(str(body["to_balance"]["quantity"])) == Decimal("35.5")
    assert body["from_balance"]["location_id"] == str(source)
    assert body["to_balance"]["location_id"] == str(destination)
    assert body["from_balance"]["article_id"] == str(article)
    assert body["to_balance"]["article_id"] == str(article)
    assert stock_quantity(client, article, source) == Decimal("74.5")
    assert stock_quantity(client, article, destination) == Decimal("35.5")


def test_transfer_endpoint_creates_destination_balance(stock_client):
    client, article, source, destination, _ = stock_client
    receive(client, article, source, "20")

    response = client.post("/stock/transfer", json=transfer_payload(
        article, source, destination, "7"
    ))

    assert response.status_code == 200, response.text
    assert Decimal(str(response.json()["from_balance"]["quantity"])) == Decimal("13")
    assert Decimal(str(response.json()["to_balance"]["quantity"])) == Decimal("7")
    assert stock_quantity(client, article, destination) == Decimal("7")


def test_transfer_endpoint_returns_409_without_stock_changes(stock_client):
    client, article, source, destination, _ = stock_client
    receive(client, article, source, "4")

    response = client.post("/stock/transfer", json=transfer_payload(
        article, source, destination, "5"
    ))

    assert response.status_code == 409
    assert stock_quantity(client, article, source) == Decimal("4")
    assert stock_quantity(client, article, destination) == Decimal("0")


@pytest.mark.parametrize("missing_side", ["source", "destination"])
def test_transfer_endpoint_returns_404_for_missing_location(stock_client, missing_side):
    client, article, source, destination, _ = stock_client
    if missing_side == "source":
        source = uuid4()
    else:
        destination = uuid4()
    response = client.post("/stock/transfer", json=transfer_payload(
        article, source, destination, "1"
    ))
    assert response.status_code == 404


@pytest.mark.parametrize("foreign_side", ["source", "destination"])
def test_transfer_endpoint_returns_404_for_foreign_tenant_location(stock_client, foreign_side):
    client, article, source, destination, foreign = stock_client
    if foreign_side == "source":
        source = foreign
    else:
        destination = foreign
    response = client.post("/stock/transfer", json=transfer_payload(
        article, source, destination, "1"
    ))
    assert response.status_code == 404


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity"])
def test_transfer_endpoint_returns_422_for_invalid_quantity(stock_client, quantity):
    client, article, source, destination, _ = stock_client
    response = client.post("/stock/transfer", json=transfer_payload(
        article, source, destination, quantity
    ))
    assert response.status_code == 422


def test_transfer_endpoint_returns_422_for_same_locations(stock_client):
    client, article, source, _, _ = stock_client
    response = client.post("/stock/transfer", json=transfer_payload(
        article, source, source, "1"
    ))
    assert response.status_code == 422


def test_transfer_endpoint_returns_422_for_blank_reason(stock_client):
    client, article, source, destination, _ = stock_client
    response = client.post("/stock/transfer", json=transfer_payload(
        article, source, destination, "1", reason="   "
    ))
    assert response.status_code == 422


def test_transfer_endpoint_returns_422_for_invalid_uuid(stock_client):
    client, article, source, destination, _ = stock_client
    response = client.post("/stock/transfer", json={
        **transfer_payload(article, source, destination, "1"),
        "to_location_id": "not-a-uuid",
    })
    assert response.status_code == 422
