from uuid import UUID, uuid4

import pytest

from app.usecases.location import (
    CreateLocation,
    GetLocation,
    ListLocations,
    SearchLocations,
    UpdateLocation,
)
from app.domain.errors import LocationAlreadyExistsError, LocationNotFoundError
from app.fakes.repositories import (
    InMemoryLocationRepository,
)


def test_create_and_get_location():
    repository = InMemoryLocationRepository()
    tenant_id = uuid4()

    location = CreateLocation(repository)(tenant_id, "Glavno skladišče")
    loaded = GetLocation(repository)(tenant_id, location.id)

    assert isinstance(location.id, UUID)
    assert loaded == location
    assert location.tenant_id == tenant_id
    assert location.name == "Glavno skladišče"


def test_duplicate_name_is_rejected_only_within_same_tenant():
    repository = InMemoryLocationRepository()
    create = CreateLocation(repository)
    tenant_a, tenant_b = uuid4(), uuid4()

    create(tenant_a, "Glavno skladišče")

    with pytest.raises(LocationAlreadyExistsError):
        create(tenant_a, "  GLAVNO SKLADIŠČE  ")

    other = create(tenant_b, "Glavno skladišče")
    assert other.tenant_id == tenant_b


@pytest.mark.parametrize("name", ["", "   "])
def test_create_rejects_empty_name(name):
    repository = InMemoryLocationRepository()

    with pytest.raises(ValueError):
        CreateLocation(repository)(uuid4(), name)


def test_get_does_not_expose_another_tenants_location():
    repository = InMemoryLocationRepository()
    tenant_a, tenant_b = uuid4(), uuid4()
    location = CreateLocation(repository)(tenant_a, "Delavnica")

    with pytest.raises(LocationNotFoundError):
        GetLocation(repository)(tenant_b, location.id)

    with pytest.raises(LocationNotFoundError):
        GetLocation(repository)(tenant_a, uuid4())


def test_list_and_search_are_tenant_scoped():
    repository = InMemoryLocationRepository()
    create = CreateLocation(repository)
    tenant_a, tenant_b = uuid4(), uuid4()
    main = create(tenant_a, "Glavno skladišče")
    backup = create(tenant_a, "Pomožno skladišče")
    create(tenant_a, "Delavnica")
    create(tenant_b, "Tuje skladišče")

    assert len(ListLocations(repository)(tenant_a)) == 3
    assert {loc.id for loc in SearchLocations(repository)(tenant_a, "  SKLADIŠČE ")} == {
        main.id,
        backup.id,
    }
    assert SearchLocations(repository)(tenant_b, "Delavnica") == []


@pytest.mark.parametrize("query", ["", "   "])
def test_search_rejects_blank_query(query):
    repository = InMemoryLocationRepository()

    with pytest.raises(ValueError):
        SearchLocations(repository)(uuid4(), query)


def test_update_changes_name_and_allows_own_name():
    repository = InMemoryLocationRepository()
    tenant_id = uuid4()
    location = CreateLocation(repository)(tenant_id, "Delavnica")
    update = UpdateLocation(repository)

    updated = update(tenant_id, location.id, "Servisna delavnica")
    assert updated.id == location.id
    assert updated.name == "Servisna delavnica"
    assert GetLocation(repository)(tenant_id, location.id).name == "Servisna delavnica"

    assert update(tenant_id, location.id, "Servisna delavnica").id == location.id


def test_update_rejects_name_used_by_another_location():
    repository = InMemoryLocationRepository()
    tenant_id = uuid4()
    first = CreateLocation(repository)(tenant_id, "Skladišče")
    second = CreateLocation(repository)(tenant_id, "Delavnica")

    with pytest.raises(LocationAlreadyExistsError):
        UpdateLocation(repository)(tenant_id, second.id, " SKLADIŠČE ")

    assert GetLocation(repository)(tenant_id, first.id).name == "Skladišče"
    assert GetLocation(repository)(tenant_id, second.id).name == "Delavnica"


def test_update_missing_location_raises_not_found():
    with pytest.raises(LocationNotFoundError):
        UpdateLocation(InMemoryLocationRepository())(uuid4(), uuid4(), "Novo ime")
