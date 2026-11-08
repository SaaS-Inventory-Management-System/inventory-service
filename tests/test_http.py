from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.fakes.repositories import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository
)
from app.presentation.routers.health import router as health_router
from app.presentation.routers.locations import create_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(create_router(
        InMemoryLocationRepository(),
        InMemoryStockBalanceRepository()
    ))
    app.include_router(health_router)
    return TestClient(app)


def test_create_get_and_list_locations(client):
    response = client.post("/locations", json={"name": "Glavno skladišče"})
    assert response.status_code == 201
    location_id = response.json()["id"]

    loaded = client.get(f"/locations/{location_id}")
    assert loaded.status_code == 200
    assert loaded.json()["name"] == "Glavno skladišče"

    listed = client.get("/locations")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_duplicate_location_returns_409(client):
    assert client.post("/locations", json={"name": "Skladišče"}).status_code == 201
    response = client.post("/locations", json={"name": " SKLADIŠČE "})
    assert response.status_code == 409


def test_location_api_validates_input_and_missing_ids(client):
    assert client.post("/locations", json={"name": "   "}).status_code == 422
    assert client.get(f"/locations/{uuid4()}").status_code == 404
    assert client.get("/locations/not-a-uuid").status_code == 422
    assert client.get("/locations", params={"search": "  "}).status_code == 422


def test_update_search_and_conflict(client):
    first = client.post("/locations", json={"name": "Skladišče"}).json()["id"]
    second = client.post("/locations", json={"name": "Delavnica"}).json()["id"]

    updated = client.put(f"/locations/{second}", json={"name": "Servisna delavnica"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Servisna delavnica"

    result = client.get("/locations", params={"search": "DELAVNICA"})
    assert result.status_code == 200
    assert [loc["id"] for loc in result.json()] == [second]

    conflict = client.put(f"/locations/{second}", json={"name": "Skladišče"})
    assert conflict.status_code == 409
    assert client.get(f"/locations/{first}").json()["name"] == "Skladišče"


def test_all_health_routes_return_200(client):
    for path in ("/health", "/health/live", "/health/ready"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["status"] in {"ok", "alive", "ready"}
