from uuid import UUID, uuid4

from app.domain.entities import Location
from app.domain.ports import LocationRepository, StockBalanceRepository

from app.domain.errors import (
    LocationNotFoundError, 
    LocationAlreadyExistsError,
    LocationInUseError
)

class CreateLocation:
    def __init__(self, repository: LocationRepository):
        self.repository = repository

    def __call__(self, tenant_id: UUID, name: str) -> Location:
        location = Location(
            id=uuid4(),
            tenant_id=tenant_id,
            name=name
        )

        existing_location = self.repository.get_by_name(
            tenant_id, 
            location.name
        )
        if existing_location:
            raise LocationAlreadyExistsError(
                f"Location with name '{location.name}' already exists."
            )

        self.repository.save(location)

        return location
    
class GetLocation:
    def __init__(self, repository: LocationRepository):
        self.repository = repository

    def __call__(self, tenant_id: UUID, location_id: UUID) -> Location:
        location = self.repository.get_by_id(
            tenant_id,
            location_id
        )
        if location is None:
            raise LocationNotFoundError(
            f"Location with ID '{location_id}' does not exist."
        )

        return location

class ListLocations:
    def __init__(self, repository: LocationRepository):
        self.repository = repository

    def __call__(self, tenant_id: UUID) -> list[Location]:
        return self.repository.list_locations(tenant_id)

class SearchLocations:
    def __init__(self, repository: LocationRepository):
        self.repository = repository

    def __call__(self, tenant_id: UUID, query: str) -> list[Location]:
        query = query.strip()

        if not query:
            raise ValueError("The search string cannot be empty.")
        
        return self.repository.search(
            tenant_id, 
            query
        )

class UpdateLocation:
    def __init__(self, repository: LocationRepository):
        self.repository = repository

    def __call__(self, 
        tenant_id: UUID,
        location_id: UUID,
        name: str
    ) -> Location:
        location = self.repository.get_by_id(
            tenant_id,
            location_id
        )
        if location is None:
            raise LocationNotFoundError(
            f"Location with ID '{location_id}' does not exist."
        )

        updated_location = location.with_updated_details(name)

        existing_location = self.repository.get_by_name(
            tenant_id,
            name
        )

        if (
            existing_location is not None
            and existing_location.id != location_id
        ):
            raise LocationAlreadyExistsError(
                f"Location with name '{name}' already exists."
            )

        self.repository.save(updated_location)

        return updated_location

class DeleteLocation:
    def __init__(
        self, 
        location_repository: LocationRepository, 
        balance_repository: StockBalanceRepository
    ):
        self.location_repository = location_repository 
        self.balance_repository = balance_repository

    def __call__(self, tenant_id: UUID, location_id: UUID) -> None:
        location = self.location_repository.get_by_id(
            tenant_id=tenant_id,
            location_id=location_id
        )
        if location is None:
            raise LocationNotFoundError(
            f"Location with ID '{location_id}' does not exist."
        )

        balances = self.balance_repository.list_balances(
            tenant_id=tenant_id,
            location_id=location_id
        )
        if any(balance.quantity > 0 for balance in balances):
            raise LocationInUseError(
                "Cannot delete location because it contains stock."
            )
        
        deleted_location = location.mark_deleted()
        self.location_repository.save(deleted_location)