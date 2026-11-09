"""REST: DeleteLocation + historical reads after soft delete."""

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.projections import StockBalanceProjector
from app.infrastructure.repositories.in_memory import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository
)
from app.presentation.routers.locations import create_router as create_locations_router
from app.presentation.routers.stocks import create_router as create_stock_router


@pytest.fixture
def api():
    locations = InMemoryLocationRepository()
    balances = InMemoryStockBalanceRepository()
    events = InMemoryStockEventRepository()
    app = FastAPI()
    app.include_router(create_locations_router(locations, balances))
    app.include_router(create_stock_router(
        location_repository=locations, event_repository=events,
        balance_repository=balances, projector=StockBalanceProjector(),
    ))
    return TestClient(app)


def create_location(client, name="Skladišče"):
    response = client.post("/locations", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def receive(client, article_id, location_id, quantity):
    return client.post("/stock/receive", json={
        "article_id": str(article_id), "location_id": str(location_id),
        "quantity": str(quantity),
    })


def consume(client, article_id, location_id, quantity):
    return client.post("/stock/consume", json={
        "article_id": str(article_id), "location_id": str(location_id),
        "quantity": str(quantity),
    })


def test_delete_empty_location_returns_204_and_hides_it(api):
    location = create_location(api)
    deleted = api.delete(f"/locations/{location}")

    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""
    assert api.get(f"/locations/{location}").status_code == 404
    assert all(item["id"] != location for item in api.get("/locations").json())
    assert api.delete(f"/locations/{location}").status_code == 404


def test_delete_with_positive_stock_returns_409_and_preserves_location(api):
    location = create_location(api)
    article = uuid4()
    assert receive(api, article, location, "10").status_code == 200

    deleted = api.delete(f"/locations/{location}")
    assert deleted.status_code == 409, deleted.text
    assert api.get(f"/locations/{location}").status_code == 200


def test_deleted_location_history_still_accessible_but_writes_rejected(api):
    location = create_location(api)
    article = uuid4()
    assert receive(api, article, location, "10").status_code == 200
    assert consume(api, article, location, "10").status_code == 200
    assert api.delete(f"/locations/{location}").status_code == 204

    history = api.get(f"/stock/history/{location}/{article}")
    assert history.status_code == 200, history.text
    assert [ev["event_type"] for ev in history.json()] == ["received", "consumed"]
    assert receive(api, article, location, "1").status_code == 404
    assert api.get(f"/stock/balances/{location}/{article}").status_code == 404


def test_delete_invalid_and_nonexistent_ids(api):
    assert api.delete("/locations/not-a-uuid").status_code == 422
    assert api.delete(f"/locations/{uuid4()}").status_code == 404
