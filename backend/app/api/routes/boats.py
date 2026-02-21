import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app import crud
from app.api import deps
from app.api.deps import get_current_active_superuser
from app.models import (
    BoatCreate,
    BoatPublic,
    BoatsPublic,
    BoatUpdate,
)

router = APIRouter(prefix="/boats", tags=["boats"])


@router.get(
    "/",
    response_model=BoatsPublic,
    dependencies=[Depends(get_current_active_superuser)],
)
def read_boats(
    *,
    session: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve boats.
    """
    boats = crud.get_boats(session=session, skip=skip, limit=limit)
    count = crud.get_boats_count(session=session)
    return BoatsPublic(data=boats, count=count)


@router.post(
    "/",
    response_model=BoatPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_active_superuser)],
)
def create_boat(
    *,
    session: Session = Depends(deps.get_db),
    boat_in: BoatCreate,
) -> Any:
    """
    Create new boat.
    """
    try:
        boat = crud.create_boat(session=session, boat_in=boat_in)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    return boat


@router.get(
    "/{boat_id}",
    response_model=BoatPublic,
    dependencies=[Depends(get_current_active_superuser)],
)
def read_boat(
    *,
    session: Session = Depends(deps.get_db),
    boat_id: uuid.UUID,
) -> Any:
    """
    Get boat by ID.
    """
    boat = crud.get_boat(session=session, boat_id=boat_id)
    if not boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Boat with ID {boat_id} not found",
        )
    return boat


@router.put(
    "/{boat_id}",
    response_model=BoatPublic,
    dependencies=[Depends(get_current_active_superuser)],
)
def update_boat(
    *,
    session: Session = Depends(deps.get_db),
    boat_id: uuid.UUID,
    boat_in: BoatUpdate,
) -> Any:
    """
    Update a boat.
    Rejects reducing capacity below the number of passengers already booked
    on any trip that uses this boat's default capacity.
    """
    boat = crud.get_boat(session=session, boat_id=boat_id)
    if not boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Boat with ID {boat_id} not found",
        )

    # If capacity is being updated, ensure it is not below confirmed/checked-in
    # passengers for any trip-boat that uses the boat's default capacity
    # (drafts do not consume capacity)
    if boat_in.capacity is not None:
        trip_boats = crud.get_trip_boats_by_boat(session=session, boat_id=boat_id)
        for tb in trip_boats:
            if tb.max_capacity is None:
                paid_counts = crud.get_paid_ticket_count_per_boat_for_trip(
                    session=session, trip_id=tb.trip_id
                )
                booked = paid_counts.get(boat_id, 0)
                if booked > boat_in.capacity:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "This boat has passengers booked on trip(s) that use "
                            "its default capacity. Move them to another boat on "
                            "the trip (Reassign), or set a custom capacity for "
                            "the trip, before reducing the boat's capacity."
                        ),
                    )

    try:
        boat = crud.update_boat(session=session, db_obj=boat, obj_in=boat_in)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    return boat


@router.delete(
    "/{boat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_active_superuser)],
)
def delete_boat(
    *,
    session: Session = Depends(deps.get_db),
    boat_id: uuid.UUID,
) -> None:
    """
    Delete a boat.
    """
    boat = crud.get_boat(session=session, boat_id=boat_id)
    if not boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Boat with ID {boat_id} not found",
        )

    try:
        crud.delete_boat(session=session, db_obj=boat)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/jurisdiction/{jurisdiction_id}",
    response_model=BoatsPublic,
    dependencies=[Depends(get_current_active_superuser)],
)
def read_boats_by_jurisdiction(
    *,
    session: Session = Depends(deps.get_db),
    jurisdiction_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve boats for a specific jurisdiction.
    """
    # Verify that the jurisdiction exists
    jurisdiction = crud.get_jurisdiction(
        session=session, jurisdiction_id=jurisdiction_id
    )
    if not jurisdiction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Jurisdiction with ID {jurisdiction_id} not found",
        )

    boats = crud.get_boats_by_jurisdiction(
        session=session, jurisdiction_id=jurisdiction_id, skip=skip, limit=limit
    )
    count = len(boats)

    # Convert to dictionaries to break the ORM relationship chain
    # Include provider data for backward compatibility
    boat_dicts = []
    for boat in boats:
        boat_dict = {
            "id": boat.id,
            "name": boat.name,
            "slug": boat.slug,
            "capacity": boat.capacity,
            "provider_id": boat.provider_id,
            "created_at": boat.created_at,
            "updated_at": boat.updated_at,
        }
        # Add provider data if available
        if boat.provider:
            boat_dict["provider_name"] = boat.provider.name
            boat_dict["provider_location"] = boat.provider.location
            boat_dict["provider_address"] = boat.provider.address
            boat_dict["jurisdiction_id"] = boat.provider.jurisdiction_id
            boat_dict["map_link"] = boat.provider.map_link
        boat_dicts.append(boat_dict)

    return BoatsPublic(data=boat_dicts, count=count)


# Public endpoints (no authentication required)
@router.get("/public/{boat_id}", response_model=BoatPublic)
def read_public_boat(
    *,
    session: Session = Depends(deps.get_db),
    boat_id: uuid.UUID,
) -> Any:
    """
    Get boat by ID for public booking form.
    No authentication required.
    """
    boat = crud.get_boat(session=session, boat_id=boat_id)
    if not boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Boat with ID {boat_id} not found",
        )
    return boat


@router.get("/public/", response_model=BoatsPublic)
def read_public_boats(
    *,
    session: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve boats for public booking form.
    No authentication required.
    """
    boats = crud.get_boats_no_relationships(session=session, skip=skip, limit=limit)
    count = crud.get_boats_count(session=session)
    return BoatsPublic(data=boats, count=count)
