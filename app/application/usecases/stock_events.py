from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.domain.entities import StockBalance
from app.domain.events import (
    StockReceived, 
    StockConsumed, 
    StockTransferred,
    StockAdjusted
)
from app.application.ports import (
    StockEventRepository, 
    StockBalanceRepository, 
    LocationRepository
)
from app.domain.errors import (
    LocationNotFoundError,
)
from ..projections import StockBalanceProjector

class ReceiveStock:
    def __init__(
        self, 
        event_repository: StockEventRepository,
        balance_repository: StockBalanceRepository,
        location_repository: LocationRepository,
        projector: StockBalanceProjector
    ):
        self.event_repository = event_repository
        self.balance_repository = balance_repository
        self.location_repository = location_repository
        self.projector = projector
    
    def __call__(
        self,
        tenant_id: UUID,
        article_id: UUID,
        location_id: UUID,
        quantity: Decimal
    ) -> StockBalance:

        # check if location exists
        location = self.location_repository.get_by_id(
            tenant_id,
            location_id
        )
        if location is None:
            raise LocationNotFoundError(
                f"Location with ID '{location_id}' does not exist."
            )

        # create the event
        event = StockReceived(
            id=uuid4(),
            tenant_id=tenant_id,
            article_id=article_id,
            location_id=location_id,
            quantity=quantity,
            occurred_at=datetime.now(timezone.utc)
        )

        # get current balance
        current_balance = self.balance_repository.get_by_ids(
            tenant_id=tenant_id,
            article_id=article_id,
            location_id=location_id
        )

        # calculate new balance from event 
        new_balance = self.projector.apply(
            balance=current_balance,
            event=event
        )

        # append event
        self.event_repository.append(event)

        # save new balance
        self.balance_repository.save(new_balance)

        return new_balance

class ConsumeStock:
    def __init__(
        self, 
        event_repository: StockEventRepository,
        balance_repository: StockBalanceRepository,
        location_repository: LocationRepository,
        projector: StockBalanceProjector
    ):
        self.event_repository = event_repository
        self.balance_repository = balance_repository
        self.location_repository = location_repository
        self.projector = projector
    
    def __call__(
        self,
        tenant_id: UUID,
        article_id: UUID,
        location_id: UUID,
        quantity: Decimal,
        reason: str | None = None,
        reference: str | None = None
    ) -> StockBalance:
        
        # check if location exists
        location = self.location_repository.get_by_id(
            tenant_id,
            location_id
        )
        if location is None:
            raise LocationNotFoundError(
                f"Location with ID '{location_id}' does not exist."
            )

        # create the event
        event = StockConsumed(
            id=uuid4(),
            tenant_id=tenant_id,
            article_id=article_id,
            location_id=location_id,
            quantity=quantity,
            occurred_at=datetime.now(timezone.utc),
            reason=reason,
            reference=reference
        )

        # get current balance
        current_balance = self.balance_repository.get_by_ids(
            tenant_id=tenant_id,
            article_id=article_id,
            location_id=location_id
        )

        # calculate new balance from event 
        new_balance = self.projector.apply(
            balance=current_balance,
            event=event
        )

        # append event
        self.event_repository.append(event)

        # save new balance
        self.balance_repository.save(new_balance)

        return new_balance

class TransferStock:
    def __init__(
        self,
        location_repository: LocationRepository,
        event_repository: StockEventRepository,
        balance_repository: StockBalanceRepository,
        projector: StockBalanceProjector
    ):
        self.event_repository = event_repository
        self.balance_repository = balance_repository
        self.location_repository = location_repository
        self.projector = projector
    
    def __call__(
        self,
        tenant_id: UUID,
        article_id: UUID,
        from_location_id: UUID,
        to_location_id: UUID,
        quantity: Decimal,
        reason: str | None = None,
        reference: str | None = None
    ) -> tuple[StockBalance, StockBalance]:

        # check if both locations exist
        from_location = self.location_repository.get_by_id(
            tenant_id,
            from_location_id
        )
        if from_location is None:
            raise LocationNotFoundError(
                f"Location with ID '{from_location_id}' does not exist."
            )
        
        to_location = self.location_repository.get_by_id(
            tenant_id,
            to_location_id
        )
        if to_location is None:
            raise LocationNotFoundError(
                f"Location with ID '{to_location_id}' does not exist."
            )

        # create the event
        event = StockTransferred(
            id=uuid4(),
            tenant_id=tenant_id,
            article_id=article_id,
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            quantity=quantity,
            occurred_at=datetime.now(timezone.utc),
            reason=reason,
            reference=reference
        )

        # get current balances
        current_from_balance = self.balance_repository.get_by_ids(
            tenant_id=tenant_id,
            article_id=article_id,
            location_id=from_location_id
        )
        current_to_balance = self.balance_repository.get_by_ids(
            tenant_id=tenant_id,
            article_id=article_id,
            location_id=to_location_id
        )

        # calculate new balances from event 
        new_from_balance, new_to_balance = self.projector.apply_transfer(
            from_balance=current_from_balance,
            to_balance=current_to_balance,
            event=event
        )

        # append event
        self.event_repository.append(event)
        
        # save new balances
        self.balance_repository.save(new_from_balance)
        self.balance_repository.save(new_to_balance)

        return new_from_balance, new_to_balance

class AdjustStock:

    def __init__(
        self,
        location_repository: LocationRepository,
        event_repository: StockEventRepository,
        balance_repository: StockBalanceRepository,
        projector: StockBalanceProjector
    ):
        self.location_repository = location_repository
        self.event_repository = event_repository
        self.balance_repository = balance_repository
        self.projector = projector

    def __call__(
        self,
        tenant_id: UUID,
        article_id: UUID,
        location_id: UUID,
        counted_quantity: Decimal,
        reason: str,
        reference: str | None = None
    ) -> StockBalance:

        # check if location exists
        location = self.location_repository.get_by_id(
            tenant_id,
            location_id
        )
        if location is None:
            raise LocationNotFoundError(
                f"Location with ID '{location_id}' does not exist."
            )
        
        # create the event   
        event = StockAdjusted(
            id=uuid4(),
            tenant_id=tenant_id,
            article_id=article_id,
            location_id=location_id,
            counted_quantity=counted_quantity,
            occurred_at=datetime.now(timezone.utc),
            reason=reason,
            reference=reference
        )

        # update balance
        current_balance = self.balance_repository.get_by_ids(
            tenant_id=tenant_id,
            article_id=article_id,
            location_id=location_id
        )
        new_balance = self.projector.apply(
            balance=current_balance,
            event=event
        )

        # append event
        self.event_repository.append(event)
        
        # save new balance
        self.balance_repository.save(new_balance)

        return new_balance