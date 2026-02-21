import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app import crud
from app.api import deps
from app.api.deps import get_current_active_superuser
from app.models import (
    BoatPublic,
    EffectivePricingItem,
    TripBoatCreate,
    TripBoatPublic,
    TripBoatPublicWithAvailability,
    TripBoatUpdate,
)

router = APIRouter(prefix="/trip-boats", tags=["trip-boats"])


@router.post(
    "/",
    response_model=TripBoatPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_active_superuser)],
)
def create_trip_boat(
    *,
    session: Session = Depends(deps.get_db),
    trip_boat_in: TripBoatCreate,
) -> TripBoatPublic:
    """
    Create new trip boat association.
    """
    # Verify that the trip exists
    trip = crud.get_trip(session=session, trip_id=trip_boat_in.trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_boat_in.trip_id} not found",
        )

    # Verify that the boat exists
    boat = crud.get_boat(session=session, boat_id=trip_boat_in.boat_id)
    if not boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Boat with ID {trip_boat_in.boat_id} not found",
        )

    # If setting custom capacity, it must not be below confirmed/checked-in bookings
    # (drafts do not consume capacity)
    if trip_boat_in.max_capacity is not None:
        paid_counts = crud.get_paid_ticket_count_per_boat_for_trip(
            session=session, trip_id=trip_boat_in.trip_id
        )
        booked = paid_counts.get(trip_boat_in.boat_id, 0)
        if trip_boat_in.max_capacity < booked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Custom capacity ({trip_boat_in.max_capacity}) cannot be less "
                    f"than passengers already booked on this trip for this boat ({booked}). "
                    "Reassign passengers to another boat or cancel bookings first."
                ),
            )

    trip_boat = crud.create_trip_boat(session=session, trip_boat_in=trip_boat_in)
    return TripBoatPublic(
        id=trip_boat.id,
        trip_id=trip_boat.trip_id,
        boat_id=trip_boat.boat_id,
        max_capacity=trip_boat.max_capacity,
        use_only_trip_pricing=trip_boat.use_only_trip_pricing,
        created_at=trip_boat.created_at,
        updated_at=trip_boat.updated_at,
        boat=BoatPublic.model_validate(boat),
    )


@router.get(
    "/trip/{trip_id}",
    response_model=list[TripBoatPublicWithAvailability],
    dependencies=[Depends(get_current_active_superuser)],
)
def read_trip_boats_by_trip(
    *,
    session: Session = Depends(deps.get_db),
    trip_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Get all boats for a specific trip with capacity and remaining slots per boat.
    """
    trip = crud.get_trip(session=session, trip_id=trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found",
        )
    trip_boats = crud.get_trip_boats_by_trip(
        session=session, trip_id=trip_id, skip=skip, limit=limit
    )
    paid_counts = crud.get_paid_ticket_count_per_boat_for_trip(
        session=session, trip_id=trip_id
    )
    paid_by_type = crud.get_paid_ticket_count_per_boat_per_item_type_for_trip(
        session=session, trip_id=trip_id
    )
    result: list[TripBoatPublicWithAvailability] = []
    for tb in trip_boats:
        effective_max = (
            tb.max_capacity if tb.max_capacity is not None else tb.boat.capacity
        )
        booked = paid_counts.get(tb.boat_id, 0)
        remaining = max(0, effective_max - booked)
        pricing = crud.get_effective_pricing(
            session=session,
            trip_id=trip_id,
            boat_id=tb.boat_id,
            paid_by_type=paid_by_type,
        )
        used_per_ticket_type = crud.get_ticket_item_count_per_type_for_trip_boat(
            session=session, trip_id=trip_id, boat_id=tb.boat_id
        )
        result.append(
            TripBoatPublicWithAvailability(
                trip_id=tb.trip_id,
                boat_id=tb.boat_id,
                id=tb.id,
                max_capacity=effective_max,
                use_only_trip_pricing=tb.use_only_trip_pricing,
                created_at=tb.created_at,
                updated_at=tb.updated_at,
                boat=BoatPublic.model_validate(tb.boat),
                remaining_capacity=remaining,
                pricing=pricing,
                used_per_ticket_type=used_per_ticket_type,
            )
        )
    return result


@router.get("/boat/{boat_id}", dependencies=[Depends(get_current_active_superuser)])
def read_trip_boats_by_boat(
    *,
    session: Session = Depends(deps.get_db),
    boat_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Get all trips for a specific boat.
    """
    # Verify that the boat exists
    boat = crud.get_boat(session=session, boat_id=boat_id)
    if not boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Boat with ID {boat_id} not found",
        )

    trip_boats = crud.get_trip_boats_by_boat(
        session=session, boat_id=boat_id, skip=skip, limit=limit
    )
    return trip_boats


@router.put("/{trip_boat_id}", dependencies=[Depends(get_current_active_superuser)])
def update_trip_boat(
    *,
    session: Session = Depends(deps.get_db),
    trip_boat_id: uuid.UUID,
    trip_boat_in: TripBoatUpdate,
) -> Any:
    """
    Update a trip boat association.
    """
    trip_boat = crud.get_trip_boat(session=session, trip_boat_id=trip_boat_id)
    if not trip_boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip Boat with ID {trip_boat_id} not found",
        )

    # If trip_id is being updated, verify that the new trip exists
    if trip_boat_in.trip_id is not None:
        trip = crud.get_trip(session=session, trip_id=trip_boat_in.trip_id)
        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trip with ID {trip_boat_in.trip_id} not found",
            )

    # If boat_id is being updated, verify that the new boat exists
    if trip_boat_in.boat_id is not None:
        boat = crud.get_boat(session=session, boat_id=trip_boat_in.boat_id)
        if not boat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Boat with ID {trip_boat_in.boat_id} not found",
            )

    # If setting custom capacity, it must not be below confirmed/checked-in bookings
    # (drafts do not consume capacity)
    if trip_boat_in.max_capacity is not None:
        trip_id = (
            trip_boat_in.trip_id
            if trip_boat_in.trip_id is not None
            else trip_boat.trip_id
        )
        boat_id = (
            trip_boat_in.boat_id
            if trip_boat_in.boat_id is not None
            else trip_boat.boat_id
        )
        paid_counts = crud.get_paid_ticket_count_per_boat_for_trip(
            session=session, trip_id=trip_id
        )
        booked = paid_counts.get(boat_id, 0)
        if trip_boat_in.max_capacity < booked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Custom capacity ({trip_boat_in.max_capacity}) cannot be less "
                    f"than passengers already booked on this trip for this boat ({booked}). "
                    "Reassign passengers to another boat or cancel bookings first."
                ),
            )

    trip_boat = crud.update_trip_boat(
        session=session, db_obj=trip_boat, obj_in=trip_boat_in
    )
    return trip_boat


@router.delete("/{trip_boat_id}", dependencies=[Depends(get_current_active_superuser)])
def delete_trip_boat(
    *,
    session: Session = Depends(deps.get_db),
    trip_boat_id: uuid.UUID,
) -> Any:
    """
    Delete a trip boat association.
    Fails if the boat has any ticket bookings (draft or paid); reassign or cancel those first.
    """
    trip_boat = crud.get_trip_boat(session=session, trip_boat_id=trip_boat_id)
    if not trip_boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip Boat with ID {trip_boat_id} not found",
        )
    booked = crud.get_ticket_item_count_for_trip_boat(
        session=session,
        trip_id=trip_boat.trip_id,
        boat_id=trip_boat.boat_id,
    )
    if booked > 0:
        boat_name = trip_boat.boat.name if trip_boat.boat else str(trip_boat.boat_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot remove boat '{boat_name}': it has {booked} passenger(s) booked. "
                "Reassign them to another boat or cancel the bookings first."
            ),
        )
    trip_boat = crud.delete_trip_boat(session=session, trip_boat_id=trip_boat_id)
    return trip_boat


# Public endpoint (no authentication required)
@router.get(
    "/public/trip/{trip_id}",
    response_model=list[TripBoatPublicWithAvailability],
)
def read_public_trip_boats_by_trip(
    *,
    session: Session = Depends(deps.get_db),
    trip_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Get all boats for a specific trip (public endpoint for booking form).
    Validates that the trip has public or early_bird booking_mode.
    """
    trip = crud.get_trip(session=session, trip_id=trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found",
        )

    booking_mode = getattr(trip, "booking_mode", "private")
    if booking_mode == "private":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tickets are not yet available for this trip",
        )

    trip_boats = crud.get_trip_boats_by_trip_with_boat_provider(
        session=session, trip_id=trip_id, skip=skip, limit=limit
    )
    paid_counts = crud.get_paid_ticket_count_per_boat_for_trip(
        session=session, trip_id=trip_id
    )
    paid_by_type = crud.get_paid_ticket_count_per_boat_per_item_type_for_trip(
        session=session, trip_id=trip_id
    )
    result: list[TripBoatPublicWithAvailability] = []
    for tb in trip_boats:
        effective_max = (
            tb.max_capacity if tb.max_capacity is not None else tb.boat.capacity
        )
        booked = paid_counts.get(tb.boat_id, 0)
        remaining = max(0, effective_max - booked)
        pricing = crud.get_effective_pricing(
            session=session,
            trip_id=trip_id,
            boat_id=tb.boat_id,
            paid_by_type=paid_by_type,
        )
        used_per_ticket_type = crud.get_ticket_item_count_per_type_for_trip_boat(
            session=session, trip_id=trip_id, boat_id=tb.boat_id
        )
        result.append(
            TripBoatPublicWithAvailability(
                trip_id=tb.trip_id,
                boat_id=tb.boat_id,
                id=tb.id,
                max_capacity=effective_max,
                use_only_trip_pricing=tb.use_only_trip_pricing,
                created_at=tb.created_at,
                updated_at=tb.updated_at,
                boat=BoatPublic.model_validate(tb.boat),
                remaining_capacity=remaining,
                pricing=pricing,
                used_per_ticket_type=used_per_ticket_type,
            )
        )
    return result


@router.get(
    "/public/pricing",
    response_model=list[EffectivePricingItem],
)
def read_public_effective_pricing(
    *,
    session: Session = Depends(deps.get_db),
    trip_id: uuid.UUID,
    boat_id: uuid.UUID,
) -> list[EffectivePricingItem]:
    """
    Get effective ticket types and prices for a (trip_id, boat_id).
    Boat defaults (BoatPricing) merged with per-trip overrides (TripBoatPricing).
    Validates trip exists and trip booking_mode allows public booking.
    """
    trip = crud.get_trip(session=session, trip_id=trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found",
        )
    booking_mode = getattr(trip, "booking_mode", "private")
    if booking_mode == "private":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tickets are not yet available for this trip",
        )
    paid_by_type = crud.get_paid_ticket_count_per_boat_per_item_type_for_trip(
        session=session, trip_id=trip_id
    )
    return crud.get_effective_pricing(
        session=session,
        trip_id=trip_id,
        boat_id=boat_id,
        paid_by_type=paid_by_type,
    )


@router.get(
    "/pricing",
    response_model=list[EffectivePricingItem],
    dependencies=[Depends(deps.get_current_active_superuser)],
    operation_id="trip_boats_read_effective_pricing",
)
def read_effective_pricing(
    *,
    session: Session = Depends(deps.get_db),
    trip_id: uuid.UUID,
    boat_id: uuid.UUID,
) -> list[EffectivePricingItem]:
    """
    Get effective ticket types and prices for (trip_id, boat_id). Admin only.
    Use for editing booking item ticket type when trip may be private.
    """
    trip = crud.get_trip(session=session, trip_id=trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found",
        )
    paid_by_type = crud.get_paid_ticket_count_per_boat_per_item_type_for_trip(
        session=session, trip_id=trip_id
    )
    return crud.get_effective_pricing(
        session=session,
        trip_id=trip_id,
        boat_id=boat_id,
        paid_by_type=paid_by_type,
    )
