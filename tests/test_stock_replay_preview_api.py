from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.projections import StockBalanceProjector
from app.domain.entities import Location, StockBalance
from app.domain.events import StockReceived
from app.infrastructure.repositories.in_memory import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository,
)
from app.presentation.routers.stocks import create_router


@pytest.fixture
def context():
    tenant = UUID("11111111-1111-4111-8111-111111111111")
    foreign_tenant = uuid4()
    article, other_article = uuid4(), uuid4()
    source, destination = uuid4(), uuid4()
    locations = InMemoryLocationRepository()
    locations.save(Location(id=source, tenant_id=tenant, name="Skladisce"))
    locations.save(Location(id=destination, tenant_id=tenant, name="Delavnica"))
    balances = InMemoryStockBalanceRepository()
    events = InMemoryStockEventRepository()
    app = FastAPI()
    app.include_router(create_router(
        location_repository=locations,
        event_repository=events,
        balance_repository=balances,
        projector=StockBalanceProjector(),
    ))
    return {
        "client": TestClient(app),
        "tenant": tenant, "foreign_tenant": foreign_tenant,
        "article": article, "other_article": other_article,
        "source": source, "destination": destination,
        "events": events, "balances": balances,
    }


def post_or_fail(client, route, payload):
    response = client.post(route, json=payload)
    assert response.status_code == 200, response.text
    return response


def preview(client):
    return client.post("/stock/replay/preview")


def stock_map(response):
    assert response.status_code == 200, response.text
    return {
        (row["tenant_id"], row["article_id"], row["location_id"]):
        Decimal(str(row["quantity"]))
        for row in response.json()
    }


def test_preview_without_events_returns_empty_list(context):
    response = preview(context["client"])
    assert response.status_code == 200, response.text
    assert response.json() == []


def test_preview_matches_current_balances_after_receive_consume_and_transfer(context):
    c = context
    client, a, source, destination = (
        c["client"], c["article"], c["source"], c["destination"]
    )
    post_or_fail(client, "/stock/receive", {
        "article_id": str(a), "location_id": str(source), "quantity": "100",
    })
    post_or_fail(client, "/stock/consume", {
        "article_id": str(a), "location_id": str(source), "quantity": "10",
    })
    post_or_fail(client, "/stock/transfer", {
        "article_id": str(a), "from_location_id": str(source),
        "to_location_id": str(destination), "quantity": "25",
    })
    post_or_fail(client, "/stock/consume", {
        "article_id": str(a), "location_id": str(destination), "quantity": "5",
    })
    post_or_fail(client, "/stock/receive", {
        "article_id": str(c["other_article"]),
        "location_id": str(source), "quantity": "3.5",
    })

    replayed = stock_map(preview(client))
    stored = stock_map(client.get("/stock/balances"))
    assert replayed == stored == {
        (str(c["tenant"]), str(a), str(source)): Decimal("65"),
        (str(c["tenant"]), str(a), str(destination)): Decimal("20"),
        (str(c["tenant"]), str(c["other_article"]), str(source)): Decimal("3.5"),
    }


def test_preview_ignores_foreign_tenant_events(context):
    c = context
    foreign_event = StockReceived(
        id=uuid4(), tenant_id=c["foreign_tenant"],
        article_id=c["article"], location_id=c["source"],
        quantity=Decimal("999"), occurred_at=datetime.now(timezone.utc),
    )
    c["events"].append(foreign_event)
    assert preview(c["client"]).json() == []


def test_preview_does_not_modify_event_store_or_stored_balances(context):
    c = context
    client, a, source = c["client"], c["article"], c["source"]
    post_or_fail(client, "/stock/receive", {
        "article_id": str(a), "location_id": str(source), "quantity": "12",
    })
    c["balances"].save(StockBalance(
        tenant_id=c["tenant"], article_id=a, location_id=source,
        quantity=Decimal("999"),
    ))
    events_before = c["events"].list_all_events(c["tenant"])

    first = stock_map(preview(client))
    second = stock_map(preview(client))

    assert first == second == {
        (str(c["tenant"]), str(a), str(source)): Decimal("12"),
    }
    assert c["events"].list_all_events(c["tenant"]) == events_before
    assert c["balances"].get_by_ids(c["tenant"], a, source).quantity == Decimal("999")


def test_preview_response_contains_balance_fields(context):
    c = context
    post_or_fail(c["client"], "/stock/receive", {
        "article_id": str(c["article"]),
        "location_id": str(c["source"]), "quantity": "2.75",
    })
    response = preview(c["client"])
    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert set(row) >= {"tenant_id", "article_id", "location_id", "quantity"}
    assert row["tenant_id"] == str(c["tenant"])
    assert row["article_id"] == str(c["article"])
    assert row["location_id"] == str(c["source"])
    assert Decimal(str(row["quantity"])) == Decimal("2.75")
