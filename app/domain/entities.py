from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

@dataclass
class Location:
    id: UUID
    tenant_id: UUID
    name: str
    deleted_at: datetime | None = None

    def __post_init__(self):
        self.name = self.name.strip()

        if not self.name:
            raise ValueError("Location name cannot be left blank.")

    def with_updated_details(self, name: str) -> "Location":
        return replace(self, name=name)

    def mark_deleted(self) -> "Location":
        return replace(
            self,
            deleted_at=datetime.now(timezone.utc)
        )

@dataclass(frozen=True)
class StockBalance:
    tenant_id: UUID
    article_id: UUID
    location_id: UUID
    quantity: Decimal

    def __post_init__(self):
        if not self.quantity.is_finite() or self.quantity < 0:
            raise ValueError("Quantity must be a non-negative, finite number.")