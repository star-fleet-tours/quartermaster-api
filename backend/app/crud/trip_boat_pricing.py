"""
TripBoatPricing CRUD operations.
"""

import uuid

from sqlalchemy import update
from sqlmodel import Session, select

from app.models import (
    BookingItem,
    TripBoatPricing,
    TripBoatPricingCreate,
    TripBoatPricingUpdate,
)


def get_trip_boat_pricing(
    *, session: Session, trip_boat_pricing_id: uuid.UUID
) -> TripBoatPricing | None:
    """Get a trip boat pricing by ID."""
    return session.get(TripBoatPricing, trip_boat_pricing_id)


def get_trip_boat_pricing_by_trip_boat(
    *,
    session: Session,
    trip_boat_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> list[TripBoatPricing]:
    """Get trip boat pricing by trip_boat."""
    return session.exec(
        select(TripBoatPricing)
        .where(TripBoatPricing.trip_boat_id == trip_boat_id)
        .offset(skip)
        .limit(limit)
    ).all()


def create_trip_boat_pricing(
    *, session: Session, trip_boat_pricing_in: TripBoatPricingCreate
) -> TripBoatPricing:
    """Create a new trip boat pricing."""
    db_obj = TripBoatPricing.model_validate(trip_boat_pricing_in)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_trip_boat_pricing(
    *,
    session: Session,
    db_obj: TripBoatPricing,
    obj_in: TripBoatPricingUpdate,
) -> TripBoatPricing:
    """Update a trip boat pricing."""
    obj_data = obj_in.model_dump(exclude_unset=True)
    # Ensure capacity=0 is applied when explicitly provided (0 is valid for unrestricted)
    if "capacity" in obj_in.model_fields_set:
        obj_data["capacity"] = obj_in.capacity
    db_obj.sqlmodel_update(obj_data)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def delete_trip_boat_pricing(
    *, session: Session, trip_boat_pricing_id: uuid.UUID
) -> TripBoatPricing | None:
    """Delete a trip boat pricing."""
    trip_boat_pricing = session.get(TripBoatPricing, trip_boat_pricing_id)
    if trip_boat_pricing:
        session.delete(trip_boat_pricing)
        session.commit()
    return trip_boat_pricing


def cascade_trip_boat_ticket_type_rename(
    *,
    session: Session,
    trip_id: uuid.UUID,
    boat_id: uuid.UUID,
    old_ticket_type: str,
    new_ticket_type: str,
) -> None:
    """
    Cascade a ticket type rename from TripBoatPricing to BookingItem.
    Call after updating TripBoatPricing.ticket_type so existing bookings reflect the new name.
    """
    session.execute(
        update(BookingItem)
        .where(
            BookingItem.trip_id == trip_id,
            BookingItem.boat_id == boat_id,
            BookingItem.item_type == old_ticket_type,
            BookingItem.trip_merchandise_id.is_(None),
        )
        .values(item_type=new_ticket_type)
    )
    session.commit()
