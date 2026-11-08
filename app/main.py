from fastapi import FastAPI

from app.presentation.routers.health import router as health_router
from app.presentation.routers.locations import create_router as create_locations_router
from app.presentation.routers.stock import create_router as create_stock_router

from app.fakes.repositories import (
    InMemoryLocationRepository,
    InMemoryStockBalanceRepository,
    InMemoryStockEventRepository
)
from usecases.projections import StockBalanceProjector


app = FastAPI(title="Inventory Service")

location_repository = InMemoryLocationRepository()
event_repository = InMemoryStockEventRepository()
balance_repository = InMemoryStockBalanceRepository()
projector = StockBalanceProjector()

app.include_router(health_router)
app.include_router(create_locations_router(
    repository=location_repository,
    balance_repository=balance_repository
))
app.include_router(create_stock_router(
    location_repository=location_repository,
    event_repository=event_repository,
    balance_repository=balance_repository,
    projector=projector
))