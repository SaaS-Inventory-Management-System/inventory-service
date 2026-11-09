"""InMemoryLocationRepository: active-only queries and historical lookup."""

from uuid import uuid4

from app.domain.entities import Location
from app.infrastructure.repositories.in_memory import (
    InMemoryLocationRepository,
)


def test_deleted_location_is_hidden_from_active_queries_but_preserved():
    repo = InMemoryLocationRepository()
    tenant = uuid4()
    location = Location(id=uuid4(), tenant_id=tenant, name="Glavno skladišče")
    repo.save(location)

    deleted = location.mark_deleted()
    repo.save(deleted)

    assert deleted.deleted_at is not None
    assert repo.get_by_id(tenant, location.id) is None
    assert repo.get_by_name(tenant, "glavno SKLADIŠČE") is None
    assert repo.list_locations(tenant) == []
    assert repo.search(tenant, "skladišče") == []
    assert repo.get_by_id_including_deleted(tenant, location.id) == deleted


def test_historical_lookup_is_scoped_to_tenant():
    repo = InMemoryLocationRepository()
    own_tenant, other_tenant = uuid4(), uuid4()
    location = Location(id=uuid4(), tenant_id=own_tenant, name="Delavnica")
    repo.save(location.mark_deleted())

    assert repo.get_by_id_including_deleted(own_tenant, location.id) is not None
    assert repo.get_by_id_including_deleted(other_tenant, location.id) is None
    assert repo.get_by_id_including_deleted(own_tenant, uuid4()) is None


def test_deleted_name_can_be_reused_for_new_active_location():
    repo = InMemoryLocationRepository()
    tenant = uuid4()
    old = Location(id=uuid4(), tenant_id=tenant, name="Skladišče")
    repo.save(old.mark_deleted())

    new = Location(id=uuid4(), tenant_id=tenant, name="Skladišče")
    assert repo.get_by_name(tenant, new.name) is None
    repo.save(new)

    assert repo.get_by_name(tenant, "SKLADIŠČE") == new
    assert repo.get_by_id_including_deleted(tenant, old.id) is not None
    assert repo.list_locations(tenant) == [new]
