"""
BoatPricing CRUD operations.
"""

import uuid

from sqlalchemy import update
from sqlmodel import Session, select

from app.models import (
    BoatPricing,
    BoatPricingCreate,
    BoatPricingUpdate,
    BookingItem,
    TripBoat,
    TripBoatPricing,
)


def get_boat_pricing(
    *, session: Session, boat_pricing_id: uuid.UUID
) -> BoatPricing | None:
    """Get a boat pricing by ID."""
    return session.get(BoatPricing, boat_pricing_id)


def get_boat_pricing_by_boat(
    *, session: Session, boat_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> list[BoatPricing]:
    """Get boat pricing by boat."""
    return session.exec(
        select(BoatPricing)
        .where(BoatPricing.boat_id == boat_id)
        .offset(skip)
        .limit(limit)
    ).all()


def create_boat_pricing(
    *, session: Session, boat_pricing_in: BoatPricingCreate
) -> BoatPricing:
    """Create a new boat pricing."""
    db_obj = BoatPricing.model_validate(boat_pricing_in)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_boat_pricing(
    *, session: Session, db_obj: BoatPricing, obj_in: BoatPricingUpdate
) -> BoatPricing:
    """Update a boat pricing."""
    obj_data = obj_in.model_dump(exclude_unset=True)
    # Ensure capacity=0 is applied when explicitly provided (0 = unrestricted)
    if "capacity" in obj_in.model_fields_set:
        obj_data["capacity"] = obj_in.capacity
    db_obj.sqlmodel_update(obj_data)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def delete_boat_pricing(
    *, session: Session, boat_pricing_id: uuid.UUID
) -> BoatPricing | None:
    """Delete a boat pricing."""
    boat_pricing = session.get(BoatPricing, boat_pricing_id)
    if boat_pricing:
        session.delete(boat_pricing)
        session.commit()
    return boat_pricing


def cascade_boat_ticket_type_rename(
    *,
    session: Session,
    boat_id: uuid.UUID,
    old_ticket_type: str,
    new_ticket_type: str,
) -> None:
    """
    Cascade a ticket type rename from BoatPricing to TripBoatPricing and BookingItem.
    Call after updating BoatPricing.ticket_type so existing bookings reflect the new name.
    """
    trip_boat_ids = [
        row[0]
        for row in session.exec(
            select(TripBoat.id).where(TripBoat.boat_id == boat_id)
        ).all()
    ]
    if trip_boat_ids:
        session.execute(
            update(TripBoatPricing)
            .where(
                TripBoatPricing.trip_boat_id.in_(trip_boat_ids),
                TripBoatPricing.ticket_type == old_ticket_type,
            )
            .values(ticket_type=new_ticket_type)
        )
    session.execute(
        update(BookingItem)
        .where(
            BookingItem.boat_id == boat_id,
            BookingItem.item_type == old_ticket_type,
            BookingItem.trip_merchandise_id.is_(None),
        )
        .values(item_type=new_ticket_type)
    )
    session.commit()
