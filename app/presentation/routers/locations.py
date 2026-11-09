"""Web layer: the FastAPI delivery mechanism.

It receives the injected use cases, exposes them as HTTP routes, and
translates domain errors into HTTP status codes. This is the only place that
imports FastAPI.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.domain.errors import LocationNotFoundError, LocationAlreadyExistsError, LocationInUseError
from app.application.usecases.locations import (
    GetLocation, 
    CreateLocation,
    ListLocations,
    SearchLocations,
    UpdateLocation,
    DeleteLocation
)
from app.application.ports import LocationRepository, StockBalanceRepository
from app.presentation.schemas import (
    LocationCreateRequest, 
    LocationResponse,
    LocationUpdateRequest,
)

# TEMPORARY
DEV_TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")

def create_router(
    repository: LocationRepository,
    balance_repository: StockBalanceRepository
) -> APIRouter:

    router = APIRouter(prefix="/locations", tags=["Locations"])

    # usecases
    create_location_use_case = CreateLocation(repository)
    get_location_use_case = GetLocation(repository)
    list_locations_use_case = ListLocations(repository)
    search_locations_use_case = SearchLocations(repository)
    update_location_use_case = UpdateLocation(repository)
    delete_location_use_case = DeleteLocation(
        repository,
        balance_repository
    )

    @router.post("", response_model=LocationResponse, status_code=201)
    def create_location(request: LocationCreateRequest):
        try:
            location = create_location_use_case(
                tenant_id=DEV_TENANT_ID,
                name=request.name,
            )
        except LocationAlreadyExistsError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error)
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error)
            ) from error
        
        return location

    @router.get("/{location_id}", response_model=LocationResponse)
    def get_location(location_id: UUID):
        try:
            location = get_location_use_case(
                tenant_id=DEV_TENANT_ID,
                location_id=location_id
            )
        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error

        return location

    @router.get("", response_model=list[LocationResponse])
    def list_locations(search: str | None = None):

        if search is None:
            return list_locations_use_case(
                tenant_id=DEV_TENANT_ID
            )

        try:
            return search_locations_use_case(
                tenant_id=DEV_TENANT_ID,
                query=search
            )

        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error)
            ) from error

    @router.put("/{location_id}", response_model=LocationResponse)
    def update_location(
        location_id: UUID,
        request: LocationUpdateRequest
    ):
        try:
            return update_location_use_case(
                tenant_id=DEV_TENANT_ID,
                location_id=location_id,
                name=request.name
            )
        
        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error
        
        except LocationAlreadyExistsError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error)
            ) from error

        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error)
            ) from error

    @router.delete("/{location_id}", status_code=204)
    def delete_location(location_id: UUID):
        try:
            delete_location_use_case(
                tenant_id=DEV_TENANT_ID,
                location_id=location_id
            )

        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error
        except LocationInUseError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error)
            ) from error

    @router.delete("/{location_id}", status_code=204)
    def delete_location(location_id: UUID):
        try:
            delete_location_use_case(
                tenant_id=DEV_TENANT_ID,
                location_id=location_id
            )

        except LocationNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error)
            ) from error
        except LocationInUseError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error)
            ) from error
        
    return router


