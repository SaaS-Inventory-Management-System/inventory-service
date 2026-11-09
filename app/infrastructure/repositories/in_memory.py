from uuid import UUID

from app.application.ports import LocationRepository, StockEventRepository, StockBalanceRepository
from app.domain.entities import Location, StockBalance
from app.domain.events import StockEvent, StockTransferred

class InMemoryLocationRepository(LocationRepository):

    def __init__(self):
        self._locations: dict[UUID, Location] = {}

    def save(self, location: Location) -> None:
        self._locations[location.id] = location

    def get_by_name(
        self,
        tenant_id: UUID,
        name: str
    ) -> Location | None:

        normalized_name = name.strip().casefold()

        for location in self._locations.values():
            if (
                location.tenant_id == tenant_id
                and location.deleted_at is None
                and location.name.strip().casefold() == normalized_name
            ):
                return location

        return None

    def get_by_id(
        self,
        tenant_id: UUID,
        location_id: UUID
    ) -> Location | None:

        location = self._locations.get(location_id)

        if (
            location is None
            or location.tenant_id != tenant_id
            or location.deleted_at is not None
        ):
            return None

        return location

    def list_locations(
        self,
        tenant_id: UUID
    ) -> list[Location]:

        return [
            location
            for location in self._locations.values()
            if (
                location.tenant_id == tenant_id
                and location.deleted_at is None
            )
        ]

    def search(
        self,
        tenant_id: UUID,
        query: str
    ) -> list[Location]:

        normalized_query = query.strip().casefold()

        return [
            location
            for location in self._locations.values()
            if (
                location.tenant_id == tenant_id
                and location.deleted_at is None
                and normalized_query in location.name.casefold()
            )
        ]

    def get_by_id_including_deleted(
        self,
        tenant_id: UUID,
        location_id: UUID
    ) -> Location | None:

        location = self._locations.get(location_id)

        if location is None or location.tenant_id != tenant_id:
            return None

        return location


class InMemoryStockEventRepository(StockEventRepository):

    def __init__(self):
        self._events: list[StockEvent] = []

    def append(self, event: StockEvent) -> None:
        if any(existing.id == event.id for existing in self._events):
            raise ValueError(
                f"Stock event with ID '{event.id}' already exists."
            )

        self._events.append(event)

    def list_events(
        self,
        tenant_id: UUID,
        article_id: UUID,
        location_id: UUID
    ) -> list[StockEvent]:

        result = []

        for event in self._events:

            if (
                event.tenant_id != tenant_id
                or event.article_id != article_id
            ):
                continue

            if isinstance(event, StockTransferred):
                if location_id in (
                    event.from_location_id,
                    event.to_location_id
                ):
                    result.append(event)

            elif event.location_id == location_id:
                result.append(event)

        return result

    def list_all_events(self, tenant_id: UUID) -> list[StockEvent]:

        return [
            event
            for event in self._events
            if event.tenant_id == tenant_id
        ]


class InMemoryStockBalanceRepository(StockBalanceRepository):

    def __init__(self):
        self._balances: dict[tuple[UUID, UUID, UUID], StockBalance] = {}

    def get_by_ids(
        self,
        tenant_id: UUID,
        article_id: UUID,
        location_id: UUID
    ) -> StockBalance | None:

        key = (tenant_id, article_id, location_id)

        return self._balances.get(key)

    def save(self, balance: StockBalance) -> None:

        key = (
            balance.tenant_id,
            balance.article_id,
            balance.location_id
        )

        self._balances[key] = balance

    def list_balances(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None
    ) -> list[StockBalance]:

        return [
            balance
            for balance in self._balances.values()
            if (
                balance.tenant_id == tenant_id
                and (
                    location_id is None
                    or balance.location_id == location_id
                )
            )
        ]

