from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.domain.errors import LocationNotFoundError, InsufficientStockError
from app.domain.events import (
    StockEvent, 
    StockTransferred,
    StockConsumed,
    StockReceived,
    StockAdjusted
)
from app.application.usecases.stock_events import (
    ReceiveStock,
    ConsumeStock,
    TransferStock,
    AdjustStock
)
from app.application.usecases.stock_balances import (
    GetStockBalance,
    ListStockBalances,
    GetStockHistory,
    RebuildStockBalances
)
from app.application.projections import StockBalanceProjector
from app.application.ports import (
    LocationRepository,
    StockBalanceRepository,
    StockEventRepository
)
from app.presentation.schemas import (
    StockBalanceResponse,
    ReceiveStockRequest,
    ConsumeStockRequest,
    TransferStockRequest,
    TransferStockResponse,
    AdjustStockRequest,
    StockConsumedResponse,
    StockReceivedResponse,
    StockEventResponse,
    StockTransferredResponse,
    StockAdjustedResponse
)

# TEMPORARY
DEV_TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")


def stock_event_to_response(event: StockEvent) -> StockEventResponse:

    if isinstance(event, StockReceived):
        return StockReceivedResponse.model_validate(event)

    if isinstance(event, StockConsumed):
        return StockConsumedResponse.model_validate(event)

    if isinstance(event, StockTransferred):
        return StockTransferredResponse.model_validate(event)

    if isinstance(event, StockAdjusted):
        return StockAdjustedResponse.model_validate(event)

    raise TypeError(f"Unsupported stock event type: {type(event)}")


def create_router(
    location_repository: LocationRepository,
    event_repository: StockEventRepository,
    balance_repository: StockBalanceRepository,
    projector: StockBalanceProjector
) -> APIRouter:

    router = APIRouter(prefix="/stock", tags=["Stock"])

    # usecases
    receive_stock_use_case = ReceiveStock(
        event_repository=event_repository,
        balance_repository=balance_repository,
        location_repository=location_repository,
        projector=projector
    )
    consume_stock_use_case = ConsumeStock(
        event_repository=event_repository,
        balance_repository=balance_repository,
        location_repository=location_repository,
        projector=projector
    )
    transfer_stock_use_case = TransferStock(
        location_repository=location_repository,
        event_repository=event_repository,
        balance_repository=balance_repository,
        projector=projector
    )
    adjust_stock_use_case = AdjustStock(
        location_repository=location_repository,
        event_repository=event_repository,
        balance_repository=balance_repository,
        projector=projector
    )
    get_stock_balance_use_case = GetStockBalance(
        balance_repository=balance_repository,
        location_repository=location_repository
    )
    list_stock_balance_use_case = ListStockBalances(
        balance_repository=balance_repository,
        location_repository=location_repository
    )
    get_stock_history_use_case = GetStockHistory(
        event_repository=event_repository,
        location_repository=location_repository
    )
    rebuild_stock_balances_use_case = RebuildStockBalances(
        event_repository=event_repository,
        projector=projector
    )

    @router.post("/receive", response_model=StockBalanceResponse, status_code=200)
    def receive_stock(request: ReceiveStockRequest):
        try:
            new_balance = receive_stock_use_case(
                tenant_id=DEV_TENANT_ID,
                article_id=request.article_id,
                location_id=request.location_id,
                quantity=request.quantity
            )

        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error
        
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error)
            ) from error
        
        return new_balance

    @router.post("/consume", response_model=StockBalanceResponse, status_code=200)
    def consume_stock(request: ConsumeStockRequest):
        try:
            new_balance = consume_stock_use_case(
                tenant_id=DEV_TENANT_ID,
                article_id=request.article_id,
                location_id=request.location_id,
                quantity=request.quantity,
                reason=request.reason,
                reference=request.reference
            )

        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error

        except InsufficientStockError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error)
            ) from error

        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error)
            ) from error
        
        return new_balance

    @router.post("/transfer", response_model=TransferStockResponse, status_code=200)
    def transfer_stock(request: TransferStockRequest):
        try:
            from_stock_balance, to_stock_balance = transfer_stock_use_case(
                tenant_id=DEV_TENANT_ID,
                article_id=request.article_id,
                from_location_id=request.from_location_id,
                to_location_id=request.to_location_id,
                quantity=request.quantity,
                reason=request.reason,
                reference=request.reference
            )

        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error

        except InsufficientStockError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error)
            ) from error
        
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error)
            ) from error
        
        return TransferStockResponse(
            from_balance=from_stock_balance,
            to_balance=to_stock_balance
        )

    @router.post("/adjust", response_model=StockBalanceResponse, status_code=200)
    def adjust_stock(request: AdjustStockRequest):
        try:
            stock_balance = adjust_stock_use_case(
                tenant_id=DEV_TENANT_ID,
                article_id=request.article_id,
                location_id=request.location_id,
                counted_quantity=request.counted_quantity,
                reason=request.reason,
                reference=request.reference
            )

        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error

        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error)
            ) from error

        return stock_balance
    
    @router.get("/balances/{location_id}/{article_id}", response_model=StockBalanceResponse, status_code=200)
    def get_stock(location_id: UUID, article_id: UUID):
        try:
            stock_balance = get_stock_balance_use_case(
                tenant_id=DEV_TENANT_ID,
                article_id=article_id,
                location_id=location_id
            )

        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error

        return stock_balance

    @router.get("/balances", response_model=list[StockBalanceResponse], status_code=200)
    def list_stock_balances(location_id: UUID | None = None):
        try:
            balances = list_stock_balance_use_case(
                tenant_id=DEV_TENANT_ID,
                location_id=location_id
            )

        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error

        return balances

    @router.get("/history/{location_id}/{article_id}", response_model=list[StockEventResponse], status_code=200)
    def list_event_history(location_id: UUID, article_id: UUID):
        try:
            events = [
                stock_event_to_response(event)
                for event in get_stock_history_use_case(
                    tenant_id=DEV_TENANT_ID,
                    article_id=article_id,
                    location_id=location_id
                )
            ]
            
        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error

        return events

    @router.post("/replay/preview", response_model=list[StockBalanceResponse], status_code=200)
    def preview_stock_replay():
        return rebuild_stock_balances_use_case(
            tenant_id=DEV_TENANT_ID
        )
    
    return router