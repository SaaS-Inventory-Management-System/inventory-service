from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.entities import StockBalance
from app.domain.events import (
    StockEvent, 
    StockReceived, 
    StockConsumed, 
    StockTransferred,
    StockAdjusted
)
from app.domain.ports import (
    StockEventRepository, 
    StockBalanceRepository, 
    LocationRepository
)
from app.domain.errors import (
    LocationNotFoundError,
)
from .projections import StockBalanceProjector

class GetStockBalance:
    def __init__(
        self,
        balance_repository: StockBalanceRepository,
        location_repository: LocationRepository
    ):
        self.balance_repository = balance_repository
        self.location_repository = location_repository

    def __call__(
        self,
        tenant_id: UUID,
        article_id: UUID,
        location_id: UUID
    ) -> StockBalance:

        location = self.location_repository.get_by_id(
            tenant_id,
            location_id
        )
        if location is None:
            raise LocationNotFoundError(
                f"Location with ID '{location_id}' does not exist."
        )
        
        current_balance = self.balance_repository.get_by_ids(
            tenant_id=tenant_id,
            article_id=article_id,
            location_id=location_id
        )
        if current_balance is None:
            current_balance = StockBalance(
                tenant_id=tenant_id,
                article_id=article_id,
                location_id=location_id,
                quantity=Decimal("0")
            )

        return current_balance


class ListStockBalances:
    def __init__(
        self,
        balance_repository: StockBalanceRepository,
        location_repository: LocationRepository
    ):
        self.balance_repository = balance_repository
        self.location_repository = location_repository

    def __call__(
        self,
        tenant_id: UUID,
        location_id: UUID | None = None
    ) -> list[StockBalance]:

        if location_id is not None:
            location = self.location_repository.get_by_id(
                tenant_id,
                location_id
            )
            if location is None:
                raise LocationNotFoundError(
                    f"Location with ID '{location_id}' does not exist."
            )
                
        return self.balance_repository.list_balances(
            tenant_id=tenant_id,
            location_id=location_id
        )


class GetStockHistory:
    def __init__(
        self,
        event_repository: StockEventRepository,
        location_repository: LocationRepository
    ):
        self.event_repository = event_repository
        self.location_repository = location_repository

    def __call__(
        self,
        tenant_id: UUID,
        article_id: UUID,
        location_id: UUID
    ) -> list[StockEvent]:
        
        location = self.location_repository.get_by_id_including_deleted(
            tenant_id,
            location_id
        )
        if location is None:
            raise LocationNotFoundError(
                f"Location with ID '{location_id}' does not exist."
        )

        return self.event_repository.list_events(
            tenant_id=tenant_id,
            article_id=article_id,
            location_id=location_id
        )

# Event Sourcing replay
class RebuildStockBalances:

    def __init__(
        self,
        event_repository: StockEventRepository,
        projector: StockBalanceProjector
    ):
        self.event_repository = event_repository
        self.projector = projector

    def __call__(self, tenant_id: UUID) -> list[StockBalance]:

        # (article_id, location_id) = StockBalance
        balances: dict[tuple[UUID, UUID], StockBalance] = {}   

        # get all events from this tenant
        events = self.event_repository.list_all_events(tenant_id)

        # walk through events
        for event in events:
            if isinstance(event, (StockReceived, StockConsumed, StockAdjusted)):
                
                # get curent balance for this article at this location
                key = (event.article_id, event.location_id)
                current_balance = balances.get(key)

                # calculate new balance
                new_balance = self.projector.apply(
                    balance=current_balance,
                    event=event
                )
                balances[key] = new_balance

            elif isinstance(event, StockTransferred):

                # get curent balance for this article at FROM location
                from_key = (event.article_id, event.from_location_id)
                current_from_balance = balances.get(from_key)

                # get curent balance for this article at TO location
                to_key = (event.article_id, event.to_location_id)
                current_to_balance = balances.get(to_key)

                # calculate new balances
                new_from_balance, new_to_balance = self.projector.apply_transfer(
                    from_balance=current_from_balance,
                    to_balance=current_to_balance,
                    event=event
                )
                balances[from_key] = new_from_balance
                balances[to_key] = new_to_balance

            else:
                raise TypeError(f"Unsupported stock event type: {type(event)}")

        return list(balances.values())

