"""
Mission CRUD operations.
"""

import uuid

from sqlalchemy import bindparam, func
from sqlmodel import Session, select, text

from app.models import (
    Booking,
    BookingItem,
    Mission,
    MissionCreate,
    MissionUpdate,
    Trip,
)


def create_mission(*, session: Session, mission_in: MissionCreate) -> Mission:
    """Create a new mission."""
    db_obj = Mission.model_validate(mission_in)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def get_mission(*, session: Session, mission_id: uuid.UUID) -> Mission | None:
    """Get a mission by ID."""
    return session.get(Mission, mission_id)


def get_missions(*, session: Session, skip: int = 0, limit: int = 100) -> list[Mission]:
    """Get multiple missions."""
    return session.exec(select(Mission).offset(skip).limit(limit)).all()


def get_missions_by_launch(
    *, session: Session, launch_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> list[Mission]:
    """Get missions by launch."""
    return session.exec(
        select(Mission).where(Mission.launch_id == launch_id).offset(skip).limit(limit)
    ).all()


def get_active_missions(
    *, session: Session, skip: int = 0, limit: int = 100
) -> list[Mission]:
    """Get active missions."""
    return session.exec(
        select(Mission).where(Mission.active).offset(skip).limit(limit)
    ).all()


def get_public_missions(
    *, session: Session, skip: int = 0, limit: int = 100
) -> list[Mission]:
    """Get missions that have at least one trip with public or early_bird booking_mode."""
    return session.exec(
        select(Mission)
        .join(Trip, Trip.mission_id == Mission.id)
        .where(Trip.booking_mode.in_(["public", "early_bird"]))
        .distinct()
        .offset(skip)
        .limit(limit)
    ).all()


def get_missions_no_relationships(
    *, session: Session, skip: int = 0, limit: int = 100
) -> list[dict]:
    """
    Get missions without loading relationships.
    Returns dictionaries with mission data.
    """

    result = session.exec(
        text(
            """
            SELECT id, name, launch_id, active, refund_cutoff_hours, created_at, updated_at
            FROM mission
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :skip
        """
        ).params(limit=limit, skip=skip)
    ).all()

    missions_data = []
    for row in result:
        missions_data.append(
            {
                "id": row[0],
                "name": row[1],
                "launch_id": row[2],
                "active": row[3],
                "refund_cutoff_hours": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
        )

    return missions_data


def get_missions_count(*, session: Session) -> int:
    """Get the total count of missions."""
    count = session.exec(select(func.count(Mission.id))).first()
    return count or 0


def get_missions_with_stats(
    *, session: Session, skip: int = 0, limit: int = 100
) -> list[dict]:
    """
    Get a list of missions with booking statistics.
    Returns dictionaries with mission data plus total_bookings and total_sales.
    """

    # Get all missions with location timezone (mission->launch->location)
    missions_result = session.exec(
        text(
            """
            SELECT m.id, m.name, m.launch_id, m.active,
                   m.refund_cutoff_hours, m.created_at, m.updated_at, loc.timezone
            FROM mission m
            JOIN launch l ON m.launch_id = l.id
            JOIN location loc ON l.location_id = loc.id
            ORDER BY m.created_at DESC
            LIMIT :limit OFFSET :skip
        """
        ).params(limit=limit, skip=skip)
    ).all()

    result = []
    for mission_row in missions_result:
        mission_id = mission_row[0]
        mission_name = mission_row[1]
        launch_id = mission_row[2]
        active = mission_row[3]
        refund_cutoff_hours = mission_row[4]
        created_at = mission_row[5]
        updated_at = mission_row[6]
        timezone_val = mission_row[7] or "UTC"

        # Get all trips for this mission (just IDs to avoid relationship loading)
        trips_statement = select(Trip.id).where(Trip.mission_id == mission_id)
        trip_results = session.exec(trips_statement).unique().all()
        trip_ids = list(trip_results)

        # Calculate total bookings and sales for all trips in this mission
        if trip_ids:
            # Count unique bookings (not booking items) for this mission's trips
            # Only include confirmed, checked_in, and completed bookings (actual revenue)
            bookings_statement = (
                select(func.count(func.distinct(Booking.id)))
                .select_from(Booking)
                .join(BookingItem, Booking.id == BookingItem.booking_id)
                .where(BookingItem.trip_id.in_(trip_ids))
                .where(
                    Booking.booking_status.in_(["confirmed", "checked_in", "completed"])
                )
            )
            total_bookings = session.exec(bookings_statement).first() or 0

            # Sum total sales for this mission's trips (excluding tax).
            # Use proportional allocation to avoid double-counting when a booking
            # has multiple items for the same trip or items across multiple trips.
            sales_statement = text(
                """
                    SELECT COALESCE(SUM(
                        CASE WHEN b.subtotal > 0
                        THEN (trip_items.trip_item_subtotal::float / b.subtotal)
                             * (b.total_amount - b.tax_amount)
                        ELSE 0 END
                    ), 0)
                    FROM (
                        SELECT bi.booking_id,
                               SUM(bi.quantity * bi.price_per_unit) AS trip_item_subtotal
                        FROM bookingitem bi
                        WHERE bi.trip_id IN :trip_ids
                          AND bi.status IN ('active', 'fulfilled')
                        GROUP BY bi.booking_id
                    ) trip_items
                    JOIN booking b ON b.id = trip_items.booking_id
                    WHERE b.booking_status IN ('confirmed', 'checked_in', 'completed')
                    """
            ).bindparams(bindparam("trip_ids", expanding=True))
            sales_row = session.exec(
                sales_statement, params={"trip_ids": trip_ids}
            ).first()
            total_sales = float(sales_row[0]) if sales_row is not None else 0.0  # cents
        else:
            total_bookings = 0
            total_sales = 0  # cents

        result.append(
            {
                "id": mission_id,
                "name": mission_name,
                "launch_id": launch_id,
                "active": active,
                "refund_cutoff_hours": refund_cutoff_hours,
                "created_at": created_at,
                "updated_at": updated_at,
                "timezone": timezone_val,
                "trip_count": len(trip_ids),
                "total_bookings": total_bookings,
                "total_sales": float(total_sales),
            }
        )

    return result


def update_mission(
    *, session: Session, db_obj: Mission, obj_in: MissionUpdate
) -> Mission:
    """Update a mission."""
    obj_data = obj_in.model_dump(exclude_unset=True)
    db_obj.sqlmodel_update(obj_data)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def delete_mission(*, session: Session, db_obj: Mission) -> None:
    """Delete a mission. Fails if any trips reference it."""
    trips_count = (
        session.exec(
            select(func.count(Trip.id)).where(Trip.mission_id == db_obj.id)
        ).first()
        or 0
    )
    if trips_count > 0:
        raise ValueError(
            f"Cannot delete this mission: {trips_count} trip(s) are associated. Remove those trips first."
        )
    session.delete(db_obj)
    session.commit()
