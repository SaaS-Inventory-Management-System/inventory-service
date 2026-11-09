from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TypeAlias
from uuid import UUID

@dataclass(frozen=True)
class StockReceived:
    id: UUID
    tenant_id: UUID
    article_id: UUID
    location_id: UUID
    quantity: Decimal
    occurred_at: datetime

    def __post_init__(self):
        if not self.quantity.is_finite() or self.quantity <= 0:
            raise ValueError("Quantity must be a positive, finite number.")

@dataclass(frozen=True)
class StockConsumed:
    id: UUID
    tenant_id: UUID
    article_id: UUID
    location_id: UUID
    quantity: Decimal
    occurred_at: datetime
    reason: str | None = None
    reference: str | None = None

    def __post_init__(self):
        if not self.quantity.is_finite() or self.quantity <= 0:
            raise ValueError("Quantity must be a positive, finite number.")

        if self.reason is not None and not self.reason.strip():
            raise ValueError("Reason cannot be empty.")

@dataclass(frozen=True)
class StockTransferred:
    id: UUID
    tenant_id: UUID
    article_id: UUID
    from_location_id: UUID
    to_location_id: UUID
    quantity: Decimal
    occurred_at: datetime
    reason: str | None = None
    reference: str | None = None

    def __post_init__(self):
        if self.from_location_id == self.to_location_id:
            raise ValueError(
                "Source and destination locations must be different."
            )

        if not self.quantity.is_finite() or self.quantity <= 0:
            raise ValueError("Quantity must be a positive, finite number.")

        if self.reason is not None and not self.reason.strip():
            raise ValueError("Reason cannot be empty.")

@dataclass(frozen=True)
class StockAdjusted:
    id: UUID
    tenant_id: UUID
    article_id: UUID
    location_id: UUID
    counted_quantity: Decimal
    occurred_at: datetime
    reason: str
    reference: str | None = None

    def __post_init__(self):
        if not self.counted_quantity.is_finite() or self.counted_quantity < 0:
            raise ValueError("Counted quantity must be a non-negative, finite number.")

        if not self.reason.strip():
            raise ValueError("Reason cannot be empty.")

StockEvent: TypeAlias = StockReceived | StockConsumed | StockTransferred | StockAdjusted