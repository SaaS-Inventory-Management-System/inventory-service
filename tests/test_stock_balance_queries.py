"""Use Case tests for GetStockBalance and ListStockBalances."""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.usecases.stock_balance import GetStockBalance, ListStockBalances
from app.domain.entities import Location, StockBalance
from app.domain.errors import LocationNotFoundError
from app.fakes.repositories import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
)


@pytest.fixture
def context():
    tenant_a, tenant_b = uuid4(), uuid4()
    location_a1, location_a2, location_b = uuid4(), uuid4(), uuid4()
    article_1, article_2 = uuid4(), uuid4()

    locations = InMemoryLocationRepository()
    balances = InMemoryStockBalanceRepository()
    locations.save(Location(id=location_a1, tenant_id=tenant_a, name="Skladišče"))
    locations.save(Location(id=location_a2, tenant_id=tenant_a, name="Delavnica"))
    locations.save(Location(id=location_b, tenant_id=tenant_b, name="Tuje skladišče"))

    for tenant, article, location, quantity in (
        (tenant_a, article_1, location_a1, "50"),
        (tenant_a, article_2, location_a1, "12.5"),
        (tenant_a, article_1, location_a2, "7"),
        (tenant_b, article_1, location_b, "999"),
    ):
        balances.save(StockBalance(
            tenant_id=tenant,
            article_id=article,
            location_id=location,
            quantity=Decimal(quantity),
        ))

    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "location_a1": location_a1,
        "location_a2": location_a2,
        "location_b": location_b,
        "article_1": article_1,
        "article_2": article_2,
        "balances": balances,
        "get": GetStockBalance(balances, locations),
        "list": ListStockBalances(balances, locations),
    }


def test_get_existing_balance(context):
    c = context
    result = c["get"](c["tenant_a"], c["article_1"], c["location_a1"])
    assert result.quantity == Decimal("50")
    assert result.tenant_id == c["tenant_a"]
    assert result.article_id == c["article_1"]
    assert result.location_id == c["location_a1"]


def test_get_missing_balance_returns_zero_without_saving(context):
    c = context
    unknown_article = uuid4()

    result = c["get"](c["tenant_a"], unknown_article, c["location_a1"])

    assert result.quantity == Decimal("0")
    assert result.article_id == unknown_article
    assert c["balances"].get_by_ids(
        c["tenant_a"], unknown_article, c["location_a1"]
    ) is None
    assert len(c["list"](c["tenant_a"])) == 3


def test_get_rejects_missing_or_other_tenants_location(context):
    c = context
    with pytest.raises(LocationNotFoundError):
        c["get"](c["tenant_a"], c["article_1"], uuid4())
    with pytest.raises(LocationNotFoundError):
        c["get"](c["tenant_a"], c["article_1"], c["location_b"])


def test_list_all_is_scoped_to_tenant(context):
    c = context
    result = c["list"](c["tenant_a"])

    assert len(result) == 3
    assert {b.location_id for b in result} == {c["location_a1"], c["location_a2"]}
    assert all(b.tenant_id == c["tenant_a"] for b in result)
    assert c["list"](c["tenant_b"])[0].quantity == Decimal("999")


def test_list_filter_by_location(context):
    c = context
    result = c["list"](c["tenant_a"], c["location_a1"])

    assert len(result) == 2
    assert {b.article_id for b in result} == {c["article_1"], c["article_2"]}
    assert all(b.location_id == c["location_a1"] for b in result)


def test_list_empty_location_returns_empty_list(context):
    c = context
    empty_location = uuid4()
    locations = InMemoryLocationRepository()
    locations.save(Location(id=empty_location, tenant_id=c["tenant_a"], name="Prazna lokacija"))
    list_use_case = ListStockBalances(c["balances"], locations)

    assert list_use_case(c["tenant_a"], empty_location) == []


def test_list_rejects_missing_or_other_tenants_location(context):
    c = context
    with pytest.raises(LocationNotFoundError):
        c["list"](c["tenant_a"], uuid4())
    with pytest.raises(LocationNotFoundError):
        c["list"](c["tenant_a"], c["location_b"])
