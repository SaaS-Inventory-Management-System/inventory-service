from abc import ABC, abstractmethod
from uuid import UUID

from .entities import Location, StockBalance
from .events import StockEvent

class LocationRepository(ABC):
    @abstractmethod
    def get_by_name(self, tenant_id: UUID, name: str) -> Location | None:
        ...

    @abstractmethod
    def save(self, location: Location) -> None:
        ...

    @abstractmethod
    def get_by_id(self, tenant_id: UUID, location_id: UUID) -> Location | None:
        ...

    @abstractmethod
    def list_locations(self, tenant_id: UUID) -> list[Location]:
        ...

    @abstractmethod
    def search(self, tenant_id: UUID, query: str) -> list[Location]:
        ...

    @abstractmethod
    def get_by_id_including_deleted(
        self,
        tenant_id: UUID,
        location_id: UUID
    ) -> Location | None:
        ...


class StockEventRepository(ABC):
    @abstractmethod
    def append(self, event: StockEvent) -> None:
        pass

    @abstractmethod
    def list_events(
        self,
        tenant_id: UUID,
        article_id: UUID,
        location_id: UUID
    ) -> list[StockEvent]:
        pass

    @abstractmethod
    def list_all_events(self, tenant_id: UUID) -> list[StockEvent]:
        pass


class StockBalanceRepository(ABC):
    @abstractmethod
    def get_by_ids(
        self,
        tenant_id: UUID,
        article_id: UUID,
        location_id: UUID
    ) -> StockBalance | None:
        pass

    @abstractmethod
    def save(self, balance: StockBalance) -> None:
        pass

    @abstractmethod
    def list_balances(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None
    ) -> list[StockBalance]:
        pass