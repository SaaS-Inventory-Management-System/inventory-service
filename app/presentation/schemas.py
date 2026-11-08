from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# LOCATION
class LocationCreateRequest(BaseModel):
    name: str
    
class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str

class LocationUpdateRequest(BaseModel):
    name: str

# STOCK
class ReceiveStockRequest(BaseModel):
    article_id: UUID
    location_id: UUID
    quantity: Decimal

class ConsumeStockRequest(BaseModel):
    article_id: UUID
    location_id: UUID
    quantity: Decimal
    reason: str | None = None
    reference: str | None = None
    
class StockBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    tenant_id: UUID
    article_id: UUID
    location_id: UUID
    quantity: Decimal

class TransferStockRequest(BaseModel):
    article_id: UUID
    from_location_id: UUID
    to_location_id: UUID
    quantity: Decimal
    reason: str | None = None
    reference: str | None = None

class TransferStockResponse(BaseModel):
    from_balance: StockBalanceResponse
    to_balance: StockBalanceResponse

class AdjustStockRequest(BaseModel):
    article_id: UUID
    location_id: UUID
    counted_quantity: Decimal
    reason: str
    reference: str | None = None

# EVENTS
class StockEventBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    article_id: UUID
    quantity: Decimal
    occurred_at: datetime

class StockReceivedResponse(StockEventBaseResponse):
    event_type: Literal["received"] = "received"
    location_id: UUID

class StockConsumedResponse(StockEventBaseResponse):
    event_type: Literal["consumed"] = "consumed"
    location_id: UUID
    reason: str | None = None
    reference: str | None = None

class StockTransferredResponse(StockEventBaseResponse):
    event_type: Literal["transferred"] = "transferred"
    from_location_id: UUID
    to_location_id: UUID
    reason: str | None = None
    reference: str | None = None

class StockAdjustedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    article_id: UUID
    location_id: UUID
    counted_quantity: Decimal
    occurred_at: datetime
    reason: str
    reference: str | None = None
    event_type: Literal["adjusted"] = "adjusted"

StockEventResponse: TypeAlias = Annotated[
    StockReceivedResponse 
    | StockConsumedResponse 
    | StockTransferredResponse 
    | StockAdjustedResponse,
    Field(discriminator="event_type")
]
