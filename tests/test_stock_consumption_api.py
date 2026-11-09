"""FastAPI tests for POST /stock/consume."""

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
    # Stock router currently uses DEV_TENANT_ID.
    tenant = UUID("11111111-1111-4111-8111-111111111111")
    location, article = uuid4(), uuid4()
    locations = InMemoryLocationRepository()
    locations.save(Location(id=location, tenant_id=tenant, name="Skladišče"))

    app = FastAPI()
    app.include_router(create_router(
        location_repository=locations,
        event_repository=InMemoryStockEventRepository(),
        balance_repository=InMemoryStockBalanceRepository(),
        projector=StockBalanceProjector(),
    ))
    return TestClient(app), article, location


def payload(article, location, quantity, **other):
    return {
        "article_id": str(article),
        "location_id": str(location),
        "quantity": quantity,
        **other,
    }


def test_consume_endpoint_returns_updated_balance(stock_client):
    client, article, location = stock_client
    assert client.post(
        "/stock/receive", json=payload(article, location, "40")
    ).status_code == 200

    response = client.post(
        "/stock/consume",
        json=payload(article, location, "15.5", reason="Servis", reference="DN-12"),
    )
    assert response.status_code == 200
    assert Decimal(response.json()["quantity"]) == Decimal("24.5")
    assert response.json()["article_id"] == str(article)
    assert response.json()["location_id"] == str(location)


def test_consume_endpoint_returns_409_if_insufficient_stock(stock_client):
    client, article, location = stock_client
    response = client.post(
        "/stock/consume", json=payload(article, location, "1")
    )
    assert response.status_code == 409


def test_consume_endpoint_returns_404_for_missing_location(stock_client):
    client, article, _ = stock_client
    response = client.post(
        "/stock/consume", json=payload(article, uuid4(), "1")
    )
    assert response.status_code == 404


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN"])
def test_consume_endpoint_returns_422_for_invalid_quantity(stock_client, quantity):
    client, article, location = stock_client
    response = client.post(
        "/stock/consume", json=payload(article, location, quantity)
    )
    assert response.status_code == 422
