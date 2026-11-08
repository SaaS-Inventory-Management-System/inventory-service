from dataclasses import replace
from decimal import Decimal

from app.domain.entities import StockBalance
from app.domain.events import (
    StockReceived, 
    StockConsumed, 
    StockTransferred,
    StockAdjusted
)
from app.domain.errors import (
    InsufficientStockError,
)

class StockBalanceProjector:

    def apply(
        self,
        balance: StockBalance | None,
        event: StockReceived | StockConsumed | StockAdjusted
    ) -> StockBalance:

        if balance is not None:
            if (
                event.tenant_id != balance.tenant_id or
                event.article_id != balance.article_id or
                event.location_id != balance.location_id
            ):
                raise ValueError(
                    "Stock balance and event must belong to the same tenant, article, and location."
                )
            
        if isinstance(event, StockReceived):
            
            if balance is None:
                return StockBalance(
                    tenant_id=event.tenant_id,
                    article_id=event.article_id,
                    location_id=event.location_id,
                    quantity=event.quantity
                )
            
            new_quantity = balance.quantity + event.quantity
            return replace(balance, quantity=new_quantity)  

        elif isinstance(event, StockConsumed):

            if (
                balance is None or
                event.quantity > balance.quantity
            ):
                raise InsufficientStockError(
                    "Insufficient stock available for consumption."
                )

            new_quantity = balance.quantity - event.quantity
            return replace(balance, quantity=new_quantity) 

        elif isinstance(event, StockAdjusted):
            
            if balance is None:
                return StockBalance(
                    tenant_id=event.tenant_id,
                    article_id=event.article_id,
                    location_id=event.location_id,
                    quantity=event.counted_quantity
                )
            
            return replace(balance, quantity=event.counted_quantity)
        
        raise TypeError(
            f"Unsupported stock event type: {type(event).__name__}"
        )

    def apply_transfer(
        self,
        from_balance: StockBalance | None,
        to_balance: StockBalance | None,
        event: StockTransferred
    ) -> tuple[StockBalance, StockBalance]:
        
        if (
            from_balance is None or
            from_balance.quantity < event.quantity
        ):
            raise InsufficientStockError(
                "Insufficient stock available at the source location."
            )

        if (
            event.tenant_id != from_balance.tenant_id or
            event.article_id != from_balance.article_id or
            event.from_location_id != from_balance.location_id
        ):
            raise ValueError(
                "Stock balance and event must belong to the same tenant, article, and location."
            )

        if to_balance is not None:
            if (
                event.tenant_id != to_balance.tenant_id or
                event.article_id != to_balance.article_id or
                event.to_location_id != to_balance.location_id
            ):
                raise ValueError(
                    "Stock balance and event must belong to the same tenant, article, and location."
                )
        else:
            to_balance = StockBalance(
                tenant_id=event.tenant_id,
                article_id=event.article_id,
                location_id=event.to_location_id,
                quantity=Decimal("0")
            )

        new_from_quantity = from_balance.quantity - event.quantity
        new_to_quantity = to_balance.quantity + event.quantity

        return (
            replace(from_balance, quantity=new_from_quantity),
            replace(to_balance, quantity=new_to_quantity) 
        ) 

        
        
