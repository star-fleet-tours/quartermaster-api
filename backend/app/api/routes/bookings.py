import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import nulls_first, or_
from sqlmodel import Session, func, select

from app import crud
from app.api import deps
from app.core.config import settings
from app.models import (
    Boat,
    Booking,
    BookingCreate,
    BookingItem,
    BookingItemCreate,
    BookingItemPublic,
    BookingItemQuantityUpdate,
    BookingItemStatus,
    BookingItemUpdate,
    BookingPublic,
    BookingStatus,
    BookingUpdate,
    DiscountCode,
    Launch,
    Merchandise,
    MerchandiseVariation,
    Mission,
    PaymentStatus,
    Trip,
    TripBoat,
    TripMerchandise,
    User,
)
from app.services.date_validator import effective_booking_mode
from app.utils import (
    generate_booking_cancelled_email,
    generate_booking_confirmation_email,
    generate_booking_refunded_email,
    send_email,
)

from .booking_utils import (
    build_experience_display_dict,
    compute_booking_totals,
    generate_qr_code,
    generate_unique_confirmation_code,
    get_booking_items_in_display_order,
    get_booking_with_items,
    get_mission_name_for_booking,
    prepare_booking_items_for_email,
    validate_confirmation_code,
)

# Set up logging
logger = logging.getLogger(__name__)


# Refund request body (POST body is more reliable than query for reason/notes)
class RefundRequest(BaseModel):
    refund_reason: str
    refund_notes: str | None = None
    refund_amount_cents: int | None = None


class RescheduleBookingRequest(BaseModel):
    """Request body for rescheduling a booking's ticket items to another trip."""

    target_trip_id: uuid.UUID
    boat_id: uuid.UUID | None = None  # Required if target trip has more than one boat


# Paginated response model
class BookingsPaginatedResponse(BaseModel):
    data: list[BookingPublic]
    total: int
    page: int
    per_page: int
    total_pages: int


router = APIRouter(prefix="/bookings", tags=["bookings"])


def _create_booking_impl(
    *,
    session: Session,
    booking_in: BookingCreate,
    current_user: User | None,
) -> Booking:
    """Create a new booking from payload; used by create_booking and duplicate_booking."""
    if not booking_in.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking must have at least one item",
        )

    # Validate all trips exist and are active, and ensure they all belong to the same mission.
    # Mission-level (not trip-level) allows future multi-trip bookings within a mission
    # (e.g. pre-launch + launch-day trips). UI currently creates single-trip bookings only.
    mission_id = None
    for item in booking_in.items:
        trip = session.get(Trip, item.trip_id)
        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trip {item.trip_id} not found",
            )
        if not trip.active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Trip {item.trip_id} is not active",
            )

        # Ensure all trips belong to the same mission
        if mission_id is None:
            mission_id = trip.mission_id
        elif trip.mission_id != mission_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All booking items must belong to trips from the same mission",
            )

    # Validate the derived mission exists and is active
    mission = session.get(Mission, mission_id)
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mission not found",
        )
    if not mission.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mission is not active",
        )

    # Enforce trip booking_mode access control (bypass for authenticated superusers)
    # Use effective mode: before sales_open_at, mode is one level more restrictive
    # so early bird codes work before general sale.
    now = datetime.now(timezone.utc)
    distinct_trip_ids = {item.trip_id for item in booking_in.items}
    trips_with_modes = [(tid, session.get(Trip, tid)) for tid in distinct_trip_ids]

    def _effective(t: Trip) -> str:
        return effective_booking_mode(
            getattr(t, "booking_mode", "private"),
            getattr(t, "sales_open_at", None),
            now,
        )

    any_private = any(_effective(t) == "private" for _, t in trips_with_modes if t)
    any_early_bird = any(
        _effective(t) == "early_bird" for _, t in trips_with_modes if t
    )
    logger.info(
        "create_booking access check: mission_id=%s any_private=%s any_early_bird=%s "
        "discount_code_id=%s current_user=%s is_superuser=%s",
        mission_id,
        any_private,
        any_early_bird,
        booking_in.discount_code_id,
        current_user.id if current_user else None,
        current_user.is_superuser if current_user else None,
    )
    if current_user and current_user.is_superuser:
        pass
    elif any_private:
        logger.warning(
            "create_booking 403: at least one trip has booking_mode=private",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tickets are not yet available for one or more trips",
        )
    elif any_early_bird:
        if not booking_in.discount_code_id:
            logger.warning(
                "create_booking 403: at least one trip is early_bird but discount_code_id is missing",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="An access code is required to book one or more trips",
            )
        discount_code = session.get(DiscountCode, booking_in.discount_code_id)
        if not discount_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid access code",
            )
        if not discount_code.is_access_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A valid access code is required to book one or more trips",
            )
        if not discount_code.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Access code is not active",
            )
        if (
            discount_code.access_code_mission_id
            and discount_code.access_code_mission_id != mission_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access code is not valid for this mission",
            )

    # Validate all boats exist and are associated with the corresponding trip
    for item in booking_in.items:
        boat = session.get(Boat, item.boat_id)
        if not boat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Boat {item.boat_id} not found",
            )

        # Ensure boat is associated with trip
        association = session.exec(
            select(TripBoat).where(
                (TripBoat.trip_id == item.trip_id) & (TripBoat.boat_id == item.boat_id)
            )
        ).first()
        if association is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Boat {item.boat_id} is not associated with trip {item.trip_id}",
            )

    # Validate pricing and inventory server-side
    for item in booking_in.items:
        # Check if this is a ticket item (not merchandise)
        # Tickets don't have trip_merchandise_id, merchandise items do
        if item.trip_merchandise_id is None:
            # Ticket pricing must match effective pricing for (trip_id, boat_id)
            effective = crud.get_effective_pricing(
                session=session,
                trip_id=item.trip_id,
                boat_id=item.boat_id,
            )
            by_type = {p.ticket_type: p.price for p in effective}
            # Match item_type or with "_ticket" suffix removed for backward compatibility
            price = by_type.get(item.item_type) or by_type.get(
                item.item_type.replace("_ticket", "")
            )
            if price is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No pricing configured for ticket type '{item.item_type}'",
                )
            if price != item.price_per_unit:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ticket price mismatch",
                )
        else:
            # Merchandise must reference a valid TripMerchandise row and have inventory
            tm = session.get(TripMerchandise, item.trip_merchandise_id)
            if not tm or tm.trip_id != item.trip_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid merchandise reference",
                )
            m = session.get(Merchandise, tm.merchandise_id)
            if not m:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Merchandise not found",
                )
            variations = crud.list_merchandise_variations_by_merchandise(
                session=session, merchandise_id=m.id
            )
            allowed = (
                [v.variant_value for v in variations if (v.variant_value or "").strip()]
                if variations
                else []
            )
            if allowed:
                if not item.variant_option or item.variant_option not in allowed:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Merchandise '{m.name}' requires a valid variant: "
                            f"one of {allowed}"
                        ),
                    )
            # Resolve variation for per-variant inventory
            variant_value = (item.variant_option or "").strip()
            variation = crud.get_merchandise_variation_by_merchandise_and_value(
                session=session,
                merchandise_id=tm.merchandise_id,
                variant_value=variant_value,
            )
            if not variation:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Merchandise '{m.name}' has no variation for "
                        f"variant '{variant_value or '(none)'}'"
                    ),
                )
            available = variation.quantity_total - variation.quantity_sold
            if tm.quantity_available_override is not None:
                available = min(available, tm.quantity_available_override)
            effective_price = (
                tm.price_override if tm.price_override is not None else m.price
            )
            if available < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Insufficient merchandise inventory",
                )
            if effective_price != item.price_per_unit:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Merchandise price mismatch",
                )

    # Validate per-ticket-type capacity: for each (trip_id, boat_id, item_type) check capacity
    ticket_quantity_by_trip_boat_type: dict[
        tuple[uuid.UUID, uuid.UUID, str], int
    ] = defaultdict(int)
    for item in booking_in.items:
        if item.trip_merchandise_id is None:
            ticket_quantity_by_trip_boat_type[
                (item.trip_id, item.boat_id, item.item_type)
            ] += item.quantity
    trip_ids = {i.trip_id for i in booking_in.items if i.trip_merchandise_id is None}
    paid_by_trip: dict[uuid.UUID, dict[tuple[uuid.UUID, str], int]] = {
        tid: crud.get_paid_ticket_count_per_boat_per_item_type_for_trip(
            session=session, trip_id=tid
        )
        for tid in trip_ids
    }
    for (
        trip_id,
        boat_id,
        item_type,
    ), new_quantity in ticket_quantity_by_trip_boat_type.items():
        capacities = crud.get_effective_capacity_per_ticket_type(
            session=session, trip_id=trip_id, boat_id=boat_id
        )
        capacity = capacities.get(item_type)
        if capacity is None and item_type not in capacities:
            boat = session.get(Boat, boat_id)
            boat_name = boat.name if boat else str(boat_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"No capacity configured for ticket type '{item_type}' on boat '{boat_name}'"
                ),
            )
        if capacity is not None:
            paid_by_type = paid_by_trip.get(trip_id, {})
            paid = sum(
                v
                for (bid, k), v in paid_by_type.items()
                if bid == boat_id and (k or "").lower() == (item_type or "").lower()
            )
            total_after = paid + new_quantity
            if total_after > capacity:
                boat = session.get(Boat, boat_id)
                boat_name = boat.name if boat else str(boat_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Boat '{boat_name}' has {capacity} seat(s) for '{item_type}' "
                        f"with {paid} already booked; requested {new_quantity} would exceed capacity"
                    ),
                )

    # Validate total boat capacity: sum of all ticket types must not exceed boat's max_capacity
    ticket_quantity_by_trip_boat: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(
        int
    )
    for item in booking_in.items:
        if item.trip_merchandise_id is None:
            ticket_quantity_by_trip_boat[(item.trip_id, item.boat_id)] += item.quantity

    # Get total paid counts per boat (across all ticket types)
    paid_total_by_trip: dict[uuid.UUID, dict[uuid.UUID, int]] = {
        tid: crud.get_paid_ticket_count_per_boat_for_trip(session=session, trip_id=tid)
        for tid in trip_ids
    }

    for (trip_id, boat_id), new_total in ticket_quantity_by_trip_boat.items():
        trip_boat = session.exec(
            select(TripBoat).where(
                TripBoat.trip_id == trip_id,
                TripBoat.boat_id == boat_id,
            )
        ).first()
        if not trip_boat:
            continue  # Already validated above
        boat = session.get(Boat, boat_id)
        effective_max = (
            trip_boat.max_capacity
            if trip_boat.max_capacity is not None
            else (boat.capacity if boat else 0)
        )
        paid_total = paid_total_by_trip.get(trip_id, {}).get(boat_id, 0)
        total_after = paid_total + new_total
        if total_after > effective_max:
            boat_name = boat.name if boat else str(boat_id)
            remaining = max(0, effective_max - paid_total)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Boat '{boat_name}' has {effective_max} total seat(s) "
                    f"with {paid_total} already booked; requested {new_total} ticket(s) "
                    f"would exceed capacity (only {remaining} remaining)"
                ),
            )

    # Don't create PaymentIntent yet - booking starts as draft

    # Use the confirmation code provided by the frontend
    confirmation_code = booking_in.confirmation_code

    # Verify the confirmation code is unique
    existing = (
        session.query(Booking)
        .filter(Booking.confirmation_code == confirmation_code)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation code already exists. Please try again.",
        )

    # Create booking as draft (no PaymentIntent yet)
    # Superusers can update booking_status to confirmed after creation via update endpoint
    booking = Booking(
        confirmation_code=confirmation_code,
        first_name=booking_in.first_name,
        last_name=booking_in.last_name,
        user_email=booking_in.user_email,
        user_phone=booking_in.user_phone,
        billing_address=booking_in.billing_address,
        subtotal=booking_in.subtotal,
        discount_amount=booking_in.discount_amount,
        tax_amount=booking_in.tax_amount,
        tip_amount=booking_in.tip_amount,
        total_amount=booking_in.total_amount,
        payment_intent_id=None,  # No PaymentIntent yet
        special_requests=booking_in.special_requests,
        admin_notes=booking_in.admin_notes,
        booking_status=BookingStatus.draft,
        payment_status=None,
        launch_updates_pref=booking_in.launch_updates_pref,
        discount_code_id=booking_in.discount_code_id,
    )

    # Create booking items (resolve variation for merchandise to set merchandise_variation_id)
    booking_items = []
    for item in booking_in.items:
        variation_id = None
        if item.trip_merchandise_id:
            tm = session.get(TripMerchandise, item.trip_merchandise_id)
            if tm:
                variation = crud.get_merchandise_variation_by_merchandise_and_value(
                    session=session,
                    merchandise_id=tm.merchandise_id,
                    variant_value=(item.variant_option or "").strip(),
                )
                if variation:
                    variation_id = variation.id
        booking_item = BookingItem(
            booking=booking,
            trip_id=item.trip_id,
            boat_id=item.boat_id,
            trip_merchandise_id=item.trip_merchandise_id,
            merchandise_variation_id=variation_id,
            item_type=item.item_type,
            quantity=item.quantity,
            price_per_unit=item.price_per_unit,
            status=item.status,
            refund_reason=item.refund_reason,
            refund_notes=item.refund_notes,
            variant_option=item.variant_option,
        )
        booking_items.append(booking_item)

    # Add all items to session
    session.add(booking)
    for item in booking_items:
        session.add(item)

    # Commit to get IDs
    session.commit()
    session.refresh(booking)

    # Update variation quantity_sold for merchandise items (no longer update Merchandise.quantity_available)
    try:
        for item in booking_items:
            if item.merchandise_variation_id:
                variation = session.get(
                    MerchandiseVariation, item.merchandise_variation_id
                )
                if variation:
                    variation.quantity_sold += item.quantity
                    session.add(variation)
        session.commit()
    except Exception:
        session.rollback()
        raise

    # Generate QR code
    booking.qr_code_base64 = generate_qr_code(booking.confirmation_code)

    # Update booking with QR code
    session.add(booking)
    session.commit()
    session.refresh(booking)
    booking.items = booking_items
    return booking


# --- Public Endpoints ---


@router.post("/", response_model=BookingPublic, status_code=status.HTTP_201_CREATED)
def create_booking(
    *,
    session: Session = Depends(deps.get_db),
    booking_in: BookingCreate,
    current_user: User | None = Depends(deps.get_optional_current_user),
) -> BookingPublic:
    """
    Create new booking (authentication optional - public or admin).
    """
    return _create_booking_impl(
        session=session,
        booking_in=booking_in,
        current_user=current_user,
    )


@router.post(
    "/id/{booking_id}/duplicate",
    response_model=BookingPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(deps.get_current_active_superuser)],
)
def duplicate_booking(
    *,
    session: Session = Depends(deps.get_db),
    booking_id: uuid.UUID,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> BookingPublic:
    """
    Duplicate a booking as a new draft (admin only).
    Copies customer data and items; new booking has status draft and a new confirmation code.
    """
    booking = session.get(Booking, booking_id)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_id} not found",
        )
    items = get_booking_items_in_display_order(session, booking.id)
    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking has no items to duplicate",
        )
    confirmation_code = generate_unique_confirmation_code(session)
    booking_in = BookingCreate(
        confirmation_code=confirmation_code,
        first_name=booking.first_name,
        last_name=booking.last_name,
        user_email=booking.user_email,
        user_phone=booking.user_phone,
        billing_address=booking.billing_address,
        subtotal=booking.subtotal,
        discount_amount=booking.discount_amount,
        tax_amount=booking.tax_amount,
        tip_amount=booking.tip_amount,
        total_amount=booking.total_amount,
        special_requests=booking.special_requests,
        launch_updates_pref=booking.launch_updates_pref,
        discount_code_id=booking.discount_code_id,
        admin_notes=booking.admin_notes,
        items=[
            BookingItemCreate(
                trip_id=item.trip_id,
                boat_id=item.boat_id,
                trip_merchandise_id=item.trip_merchandise_id,
                merchandise_variation_id=item.merchandise_variation_id,
                item_type=item.item_type,
                quantity=item.quantity,
                price_per_unit=item.price_per_unit,
                status=BookingItemStatus.active,
                refund_reason=None,
                refund_notes=None,
                variant_option=item.variant_option,
            )
            for item in items
        ],
    )
    created = _create_booking_impl(
        session=session,
        booking_in=booking_in,
        current_user=current_user,
    )
    created_items = get_booking_items_in_display_order(session, created.id)
    booking_public = BookingPublic.model_validate(created)
    booking_public.items = [BookingItemPublic.model_validate(i) for i in created_items]
    return booking_public


# --- Admin-Restricted Endpoints (use dependency for access control) ---


@router.get(
    "/",
    response_model=BookingsPaginatedResponse,
    dependencies=[Depends(deps.get_current_active_superuser)],
)
def list_bookings(
    *,
    session: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    mission_id: uuid.UUID | None = None,
    trip_id: uuid.UUID | None = None,
    boat_id: uuid.UUID | None = None,
    trip_type: str | None = None,
    booking_status: list[str] | None = Query(None),
    payment_status: list[str] | None = Query(None),
    search: str | None = None,
    sort_by: str = "created_at",
    sort_direction: str = "desc",
) -> BookingsPaginatedResponse:
    """
    List/search bookings (admin only).
    Optionally filter by mission_id, trip_id, boat_id, trip_type, booking_status, payment_status.
    booking_status and payment_status accept multiple values (include only those statuses).
    Optional search filters by confirmation_code, first_name, last_name, user_email, user_phone (case-insensitive substring).
    """
    try:
        # Parameter validation
        if skip < 0:
            logger.warning(f"Negative skip parameter provided: {skip}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Skip parameter cannot be negative",
            )

        if limit <= 0:
            logger.warning(f"Invalid limit parameter provided: {limit}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit parameter must be positive",
            )

        if limit > 500:
            logger.info(f"Limit parameter reduced from {limit} to 500")
            limit = 500  # Cap at 500 to prevent excessive queries

        # Apply text search on confirmation_code, name, email, phone (case-insensitive)
        search_term = search.strip() if search else ""
        if search_term:
            pattern = f"%{search_term}%"
            search_cond = or_(
                Booking.confirmation_code.ilike(pattern),
                Booking.first_name.ilike(pattern),
                Booking.last_name.ilike(pattern),
                Booking.user_email.ilike(pattern),
                Booking.user_phone.ilike(pattern),
            )
        else:
            search_cond = None

        # Build base query
        # When we have join filters (mission/trip/boat/trip_type) AND sort by trip_name/trip_type,
        # we must avoid SELECT DISTINCT + ORDER BY (expression not in SELECT) - PostgreSQL rejects it.
        # Use a subquery for filtered booking IDs, then select Booking by id.
        has_join_filters = mission_id or trip_id or boat_id or trip_type
        sort_by_trip = sort_by in ("trip_name", "trip_type")
        use_id_subquery = has_join_filters and sort_by_trip

        if use_id_subquery:
            # Subquery: distinct booking IDs matching all filters
            id_subq = select(Booking.id).join(
                BookingItem, BookingItem.booking_id == Booking.id
            )
            if mission_id or trip_type:
                id_subq = id_subq.join(Trip, Trip.id == BookingItem.trip_id)
                if mission_id:
                    id_subq = id_subq.where(Trip.mission_id == mission_id)
                if trip_type:
                    id_subq = id_subq.where(Trip.type == trip_type)
            if trip_id:
                id_subq = id_subq.where(BookingItem.trip_id == trip_id)
            if boat_id:
                id_subq = id_subq.where(BookingItem.boat_id == boat_id)
            if booking_status:
                id_subq = id_subq.where(Booking.booking_status.in_(booking_status))
            if payment_status:
                id_subq = id_subq.where(Booking.payment_status.in_(payment_status))
            if search_term:
                id_subq = id_subq.where(search_cond)
            id_subq = id_subq.distinct()
            base_query = select(Booking).where(Booking.id.in_(id_subq))
        else:
            base_query = select(Booking)
            if has_join_filters:
                base_query = base_query.join(
                    BookingItem, BookingItem.booking_id == Booking.id
                )
                if mission_id or trip_type:
                    base_query = base_query.join(Trip, Trip.id == BookingItem.trip_id)
                    if mission_id:
                        base_query = base_query.where(Trip.mission_id == mission_id)
                    if trip_type:
                        base_query = base_query.where(Trip.type == trip_type)
                if trip_id:
                    base_query = base_query.where(BookingItem.trip_id == trip_id)
                if boat_id:
                    base_query = base_query.where(BookingItem.boat_id == boat_id)
                base_query = base_query.distinct()
            if booking_status:
                base_query = base_query.where(
                    Booking.booking_status.in_(booking_status)
                )
            if payment_status:
                base_query = base_query.where(
                    Booking.payment_status.in_(payment_status)
                )
            if search_term:
                base_query = base_query.where(search_cond)

        if mission_id:
            logger.info(f"Filtering bookings by mission_id: {mission_id}")
        if trip_id:
            logger.info(f"Filtering bookings by trip_id: {trip_id}")
        if boat_id:
            logger.info(f"Filtering bookings by boat_id: {boat_id}")
        if trip_type:
            logger.info(f"Filtering bookings by trip_type: {trip_type}")
        if booking_status:
            logger.info(f"Filtering bookings by booking_status: {booking_status}")
        if payment_status:
            logger.info(f"Filtering bookings by payment_status: {payment_status}")
        if search_term:
            logger.info(f"Filtering bookings by search: {search_term!r}")

        # Get total count first
        total_count = 0
        try:
            count_query = select(func.count(Booking.id.distinct()))
            if mission_id or trip_id or boat_id or trip_type:
                count_query = count_query.select_from(Booking).join(
                    BookingItem, BookingItem.booking_id == Booking.id
                )
                if mission_id or trip_type:
                    count_query = count_query.join(Trip, Trip.id == BookingItem.trip_id)
                    if mission_id:
                        count_query = count_query.where(Trip.mission_id == mission_id)
                    if trip_type:
                        count_query = count_query.where(Trip.type == trip_type)
                if trip_id:
                    count_query = count_query.where(BookingItem.trip_id == trip_id)
                if boat_id:
                    count_query = count_query.where(BookingItem.boat_id == boat_id)
            if booking_status or payment_status:
                if not (mission_id or trip_id or boat_id or trip_type):
                    count_query = count_query.select_from(Booking)
            if booking_status:
                count_query = count_query.where(
                    Booking.booking_status.in_(booking_status)
                )
            if payment_status:
                count_query = count_query.where(
                    Booking.payment_status.in_(payment_status)
                )
            if search_term:
                count_query = count_query.where(search_cond)
            total_count = session.exec(count_query).first()
            logger.info(f"Total bookings count: {total_count}")
        except Exception as e:
            logger.error(f"Error counting bookings: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error counting bookings",
            )

        # Apply sorting (trip_name/trip_type use first item's trip by display order)
        if sort_by_trip:
            # Correlated subquery: trip name/type of first booking item (display order)
            first_item_trip = (
                select(Trip.name if sort_by == "trip_name" else Trip.type)
                .select_from(BookingItem)
                .join(Trip, Trip.id == BookingItem.trip_id)
                .where(BookingItem.booking_id == Booking.id)
                .order_by(
                    nulls_first(BookingItem.trip_merchandise_id.asc()),
                    BookingItem.item_type,
                    BookingItem.id,
                )
                .limit(1)
                .correlate(Booking)
                .scalar_subquery()
            )
            if sort_direction.lower() == "asc":
                order_clause = first_item_trip.asc().nulls_last()
            else:
                order_clause = first_item_trip.desc().nulls_first()
        else:
            sort_column = getattr(Booking, sort_by, Booking.created_at)
            if sort_direction.lower() == "asc":
                order_clause = sort_column.asc()
            else:
                order_clause = sort_column.desc()

        # Fetch bookings with sorting
        bookings = []
        try:
            bookings = session.exec(
                base_query.order_by(order_clause).offset(skip).limit(limit)
            ).all()
            logger.info(
                f"Retrieved {len(bookings)} bookings (skip={skip}, limit={limit}, sort_by={sort_by}, sort_direction={sort_direction})"
            )
        except Exception as e:
            logger.error(f"Database error in list_bookings: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error retrieving bookings from database",
            )

        result = []
        qr_code_updates = []

        # Process each booking
        for booking in bookings:
            try:
                items = get_booking_items_in_display_order(session, booking.id)
                booking_public = BookingPublic.model_validate(booking)
                booking_public.items = [
                    BookingItemPublic.model_validate(item) for item in items
                ]

                # Get mission and trip information from first booking item
                if items and len(items) > 0:
                    trip = session.get(Trip, items[0].trip_id)
                    if trip:
                        booking_public.mission_id = trip.mission_id
                        booking_public.trip_name = trip.name
                        booking_public.trip_type = trip.type
                        mission = session.get(Mission, trip.mission_id)
                        if mission:
                            booking_public.mission_name = mission.name

                # Flag bookings missing QR codes for batch update
                if not booking.qr_code_base64:
                    qr_code_updates.append(booking)

                result.append(booking_public)

            except Exception as e:
                # Log error but continue processing other bookings
                logger.error(f"Error processing booking {booking.id}: {str(e)}")
                continue

        # Batch update QR codes if needed
        if qr_code_updates:
            logger.info(
                f"Generating missing QR codes for {len(qr_code_updates)} bookings"
            )
            try:
                for booking in qr_code_updates:
                    booking.qr_code_base64 = generate_qr_code(booking.confirmation_code)
                    session.add(booking)
                session.commit()
            except Exception as e:
                logger.error(f"Error generating QR codes: {str(e)}")
                # Continue even if QR code generation fails
                session.rollback()

        # Return both data and total count for pagination
        return BookingsPaginatedResponse(
            data=result,
            total=total_count,
            page=(skip // limit) + 1,
            per_page=limit,
            total_pages=(total_count + limit - 1) // limit,  # Ceiling division
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Catch any unexpected exceptions
        logger.exception(f"Unexpected error in list_bookings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later.",
        )


@router.get(
    "/id/{booking_id}",
    response_model=BookingPublic,
    dependencies=[Depends(deps.get_current_active_superuser)],
)
def get_booking_by_id(
    *,
    session: Session = Depends(deps.get_db),
    booking_id: uuid.UUID,
) -> BookingPublic:
    """
    Retrieve booking details by ID (admin only).
    """
    try:
        # Fetch booking
        booking = session.get(Booking, booking_id)
        if not booking:
            logger.info(f"Booking not found with ID: {booking_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking with ID {booking_id} not found",
            )

        # Fetch items in display order (tickets first, then merch)
        items = []
        try:
            items = get_booking_items_in_display_order(session, booking.id)

            if not items:
                logger.warning(f"Booking {booking_id} has no items")
        except Exception as e:
            logger.error(f"Error retrieving items for booking {booking_id}: {str(e)}")
            # Continue without items rather than failing completely

        # Prepare response
        booking_public = BookingPublic.model_validate(booking)
        booking_public.items = [
            BookingItemPublic.model_validate(item) for item in items
        ]

        # Handle QR code generation
        if not booking.qr_code_base64:
            try:
                logger.info(f"Generating missing QR code for booking: {booking.id}")
                booking.qr_code_base64 = generate_qr_code(booking.confirmation_code)
                session.add(booking)
                session.commit()
            except Exception as e:
                logger.error(
                    f"Failed to generate QR code for booking {booking.id}: {str(e)}"
                )
                # Continue even if QR code generation fails
                session.rollback()

        return booking_public

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Catch any unexpected exceptions
        logger.exception(f"Unexpected error retrieving booking {booking_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later.",
        )


@router.delete(
    "/id/{booking_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(deps.get_current_active_superuser)],
    operation_id="bookings_delete_booking",
)
def delete_booking(
    *,
    session: Session = Depends(deps.get_db),
    booking_id: uuid.UUID,
) -> None:
    """
    Permanently delete a booking and its items (admin only).

    Returns merchandise inventory (quantity_sold / quantity_fulfilled) to
    the relevant variations. This action cannot be undone.
    """
    booking = session.get(Booking, booking_id)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with ID {booking_id} not found",
        )
    items = list(
        session.exec(
            select(BookingItem).where(BookingItem.booking_id == booking.id)
        ).all()
    )
    for item in items:
        if item.merchandise_variation_id:
            variation = session.get(MerchandiseVariation, item.merchandise_variation_id)
            if variation:
                variation.quantity_sold -= item.quantity
                variation.quantity_sold = max(0, variation.quantity_sold)
                if item.status == BookingItemStatus.fulfilled:
                    variation.quantity_fulfilled -= item.quantity
                    variation.quantity_fulfilled = max(0, variation.quantity_fulfilled)
                session.add(variation)
    session.delete(booking)
    session.commit()
    logger.info(
        f"Deleted booking {booking_id} (confirmation: {booking.confirmation_code})"
    )


@router.patch(
    "/id/{booking_id}",
    response_model=BookingPublic,
    dependencies=[Depends(deps.get_current_active_superuser)],
)
def update_booking(
    *,
    session: Session = Depends(deps.get_db),
    booking_id: uuid.UUID,
    booking_in: BookingUpdate,
) -> BookingPublic:
    """
    Update booking status or details (admin only).
    """
    try:
        # Validate input data
        update_data = booking_in.model_dump(exclude_unset=True)
        if not update_data:
            logger.warning(f"Empty update request for booking {booking_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update data provided",
            )

        # Fetch the booking
        booking = session.get(Booking, booking_id)
        if not booking:
            logger.warning(f"Attempt to update non-existent booking: {booking_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking with ID {booking_id} not found",
            )

        if booking.booking_status == BookingStatus.checked_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update a checked-in booking",
            )

        # 1. Enforce business rules
        # Disallow updates to items (raw) via PATCH; item_quantity_updates handled below
        forbidden_fields = {
            "items",
            "confirmation_code",
            "mission_id",
            "payment_intent_id",
        }
        invalid_fields = [f for f in forbidden_fields if f in update_data]
        if invalid_fields:
            logger.warning(
                f"Attempt to update forbidden fields: {', '.join(invalid_fields)}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot update these fields via PATCH: {', '.join(invalid_fields)}",
            )

        # Process item quantity updates (checked_in already rejected above)
        # Use booking_in (Pydantic model) so we get objects
        # and pop from update_data so it is not applied as a booking field
        item_quantity_updates: list[BookingItemQuantityUpdate] | None = getattr(
            booking_in, "item_quantity_updates", None
        )
        update_data.pop("item_quantity_updates", None)
        if item_quantity_updates:
            items = session.exec(
                select(BookingItem).where(BookingItem.booking_id == booking.id)
            ).all()
            qty_by_id = {u.id: u.quantity for u in item_quantity_updates}
            for u in item_quantity_updates:
                item = session.get(BookingItem, u.id)
                if not item or item.booking_id != booking.id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Booking item {u.id} not found or does not belong to this booking",
                    )
            # Validate ticket capacity with proposed quantities
            ticket_totals: dict[tuple[uuid.UUID, uuid.UUID, str], int] = defaultdict(
                int
            )
            for item in items:
                if item.trip_merchandise_id is None:
                    qty = qty_by_id.get(item.id, item.quantity)
                    ticket_totals[(item.trip_id, item.boat_id, item.item_type)] += qty
            # This booking's current ticket count per (boat_id, item_type); paid includes it, so subtract before adding proposed qty
            current_this_booking: dict[tuple[uuid.UUID, str], int] = defaultdict(int)
            for item in items:
                if item.trip_merchandise_id is None:
                    current_this_booking[
                        (item.boat_id, item.item_type)
                    ] += item.quantity
            for (trip_id, boat_id, item_type), qty in ticket_totals.items():
                capacities = crud.get_effective_capacity_per_ticket_type(
                    session=session, trip_id=trip_id, boat_id=boat_id
                )
                cap = capacities.get(item_type)
                if cap is None and item_type not in capacities:
                    boat = session.get(Boat, boat_id)
                    boat_name = boat.name if boat else str(boat_id)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"No capacity for ticket type '{item_type}' on boat '{boat_name}'",
                    )
                if cap is not None:
                    paid = crud.get_paid_ticket_count_per_boat_per_item_type_for_trip(
                        session=session, trip_id=trip_id
                    ).get((boat_id, item_type), 0)
                    paid_excluding_this = paid - current_this_booking.get(
                        (boat_id, item_type), 0
                    )
                    if paid_excluding_this + qty > cap:
                        boat = session.get(Boat, boat_id)
                        boat_name = boat.name if boat else str(boat_id)
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Boat '{boat_name}' capacity for '{item_type}' would be exceeded",
                        )
            # Apply quantity updates and merchandise inventory; quantity 0 removes the item
            for u in item_quantity_updates:
                item = session.get(BookingItem, u.id)
                if not item:
                    continue
                old_qty = item.quantity
                new_qty = u.quantity
                if new_qty == old_qty:
                    continue
                if item.merchandise_variation_id:
                    variation = session.get(
                        MerchandiseVariation, item.merchandise_variation_id
                    )
                    if variation:
                        delta = new_qty - old_qty
                        if delta > 0:
                            available = (
                                variation.quantity_total - variation.quantity_sold
                            )
                            if available < delta:
                                raise HTTPException(
                                    status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"Insufficient merchandise inventory for item {item.item_type}",
                                )
                            variation.quantity_sold += delta
                        else:
                            variation.quantity_sold -= abs(delta)
                            variation.quantity_sold = max(0, variation.quantity_sold)
                        session.add(variation)
                if new_qty == 0:
                    session.delete(item)
                else:
                    item.quantity = new_qty
                    session.add(item)
            # Recompute booking subtotal (0-qty items contribute 0; they were deleted)
            new_subtotal = sum(
                (qty_by_id.get(item.id, item.quantity) * item.price_per_unit)
                for item in items
            )
            booking.subtotal = new_subtotal
            session.add(booking)
            # Recompute tax and total from mission's jurisdiction (mission -> launch -> location -> jurisdiction)
            trip = None
            for item in items:
                if qty_by_id.get(item.id, item.quantity) > 0:
                    trip = session.get(Trip, item.trip_id)
                    break
            if trip:
                mission = session.get(Mission, trip.mission_id)
                launch = session.get(Launch, mission.launch_id) if mission else None
                tax_rate: float | None = None
                if launch is not None:
                    jurisdictions = crud.get_jurisdictions_by_location(
                        session=session, location_id=launch.location_id, limit=1
                    )
                    if jurisdictions:
                        tax_rate = jurisdictions[0].sales_tax_rate
                if tax_rate is not None:
                    new_tax, new_total = compute_booking_totals(
                        new_subtotal,
                        booking.discount_amount,
                        tax_rate,
                        booking.tip_amount,
                    )
                    update_data["tax_amount"] = new_tax
                    update_data["total_amount"] = new_total
            else:
                # All items removed; zero out tax and total
                update_data["tax_amount"] = 0
                update_data["total_amount"] = 0

        # Validate booking_status and payment_status transitions
        booking_status_changed = False
        new_booking_status = None
        old_booking_status = booking.booking_status

        if "booking_status" in update_data:
            new_booking_status = update_data["booking_status"]
            if new_booking_status != old_booking_status:
                booking_status_changed = True
                valid_transitions = {
                    BookingStatus.draft: [
                        BookingStatus.confirmed,
                        BookingStatus.cancelled,
                    ],
                    BookingStatus.confirmed: [
                        BookingStatus.checked_in,
                        BookingStatus.cancelled,
                    ],
                    BookingStatus.checked_in: [
                        BookingStatus.completed,
                        BookingStatus.cancelled,
                    ],
                    BookingStatus.completed: [BookingStatus.cancelled],
                    BookingStatus.cancelled: [],
                }
                allowed_next = valid_transitions.get(old_booking_status, [])
                if new_booking_status not in allowed_next:
                    logger.warning(
                        f"Invalid booking_status transition for booking {booking_id}: "
                        f"{old_booking_status} -> {new_booking_status}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Cannot transition from '{old_booking_status}' to '{new_booking_status}'",
                    )
                # Sync payment_status when admin sets cancelled
                if new_booking_status == BookingStatus.cancelled:
                    if "payment_status" not in update_data:
                        update_data["payment_status"] = PaymentStatus.failed

        # Tip must be non-negative
        if "tip_amount" in update_data and update_data["tip_amount"] is not None:
            if update_data["tip_amount"] < 0:
                logger.warning(
                    f"Negative tip amount in update: {update_data['tip_amount']}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Tip amount cannot be negative",
                )

        # If booking_status is being updated to cancelled, update BookingItems (refunded vs active)
        if "booking_status" in update_data:
            new_booking_status = update_data["booking_status"]
            new_payment_status = (
                update_data.get("payment_status") or booking.payment_status
            )
            if new_booking_status == BookingStatus.cancelled:
                try:
                    items = session.exec(
                        select(BookingItem).where(BookingItem.booking_id == booking.id)
                    ).all()

                    if not items:
                        logger.warning(
                            f"No items found for booking {booking_id} during status update"
                        )

                    for item in items:
                        item.status = (
                            BookingItemStatus.refunded
                            if new_payment_status
                            in (
                                PaymentStatus.refunded,
                                PaymentStatus.partially_refunded,
                            )
                            else BookingItemStatus.active
                        )
                        session.add(item)
                except Exception as e:
                    logger.error(
                        f"Error updating booking items for {booking_id}: {str(e)}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to update booking items status",
                    )

        # Only update allowed fields
        allowed_fields = {
            "booking_status",
            "payment_status",
            "special_requests",
            "tip_amount",
            "discount_amount",
            "tax_amount",
            "total_amount",
            "launch_updates_pref",
            "first_name",
            "last_name",
            "user_email",
            "user_phone",
            "billing_address",
            "admin_notes",
        }

        # Check for any fields that are not allowed
        invalid_fields = [f for f in update_data.keys() if f not in allowed_fields]
        if invalid_fields:
            logger.warning(
                f"Attempt to update invalid fields: {', '.join(invalid_fields)}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Fields not allowed for update: {', '.join(invalid_fields)}",
            )

        # Apply updates to allowed fields
        for field, value in update_data.items():
            setattr(booking, field, value)

        try:
            session.add(booking)
            session.commit()
            session.refresh(booking)
            logger.info(f"Successfully updated booking {booking_id}")

            # Send email notifications if booking_status changed to cancelled
            if (
                booking_status_changed
                and settings.emails_enabled
                and new_booking_status == BookingStatus.cancelled
            ):
                try:
                    # Get mission name
                    mission = session.get(Mission, booking.mission_id)
                    mission_name = mission.name if mission else "Unknown Mission"
                    is_refund = booking.payment_status in (
                        PaymentStatus.refunded,
                        PaymentStatus.partially_refunded,
                    )

                    if is_refund:
                        # Send refund confirmation email
                        email_data = generate_booking_refunded_email(
                            email_to=booking.user_email,
                            user_name=f"{booking.first_name} {booking.last_name}".strip(),
                            confirmation_code=booking.confirmation_code,
                            mission_name=mission_name,
                            refund_amount=booking.total_amount
                            / 100.0,  # cents to dollars for display
                        )

                        send_email(
                            email_to=booking.user_email,
                            subject=email_data.subject,
                            html_content=email_data.html_content,
                        )

                        logger.info(
                            f"Booking refund email sent to {booking.user_email}"
                        )
                    else:
                        # Send cancellation email (e.g. failed payment)
                        email_data = generate_booking_cancelled_email(
                            email_to=booking.user_email,
                            user_name=f"{booking.first_name} {booking.last_name}".strip(),
                            confirmation_code=booking.confirmation_code,
                            mission_name=mission_name,
                        )

                        send_email(
                            email_to=booking.user_email,
                            subject=email_data.subject,
                            html_content=email_data.html_content,
                        )

                        logger.info(
                            f"Booking cancellation email sent to {booking.user_email}"
                        )

                except Exception as e:
                    # Don't fail the booking update if email sending fails
                    logger.error(
                        f"Failed to send booking status update email: {str(e)}"
                    )

            items = get_booking_items_in_display_order(session, booking.id)
            booking_public = BookingPublic.model_validate(booking)
            booking_public.items = [
                BookingItemPublic.model_validate(item) for item in items
            ]

            # Generate QR code if it doesn't exist
            if not booking.qr_code_base64:
                try:
                    booking.qr_code_base64 = generate_qr_code(booking.confirmation_code)
                    session.add(booking)
                    session.commit()
                except Exception as e:
                    logger.error(
                        f"Failed to generate QR code for booking {booking.id}: {str(e)}"
                    )
                    # Continue even if QR code generation fails
                    session.rollback()

            return booking_public

        except Exception as e:
            session.rollback()
            logger.error(f"Database error during booking update: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while updating the booking",
            )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Catch any unexpected exceptions
        logger.exception(f"Unexpected error updating booking {booking_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later.",
        )


@router.patch(
    "/id/{booking_id}/items/{item_id}",
    response_model=BookingPublic,
    dependencies=[Depends(deps.get_current_active_superuser)],
    operation_id="bookings_update_booking_item",
)
def update_booking_item(
    *,
    session: Session = Depends(deps.get_db),
    booking_id: uuid.UUID,
    item_id: uuid.UUID,
    item_in: BookingItemUpdate,
) -> BookingPublic:
    """
    Update a single booking item (admin only). Change ticket type (e.g. upper to lower deck) or boat.

    Only ticket items (non-merchandise) can have item_type, price_per_unit, or boat_id changed.
    When item_type or boat_id is changed, price_per_unit is set from effective pricing and capacity is validated.
    Boat can only be changed to another boat on the same trip; target boat must have the (current or new) ticket type.
    Booking subtotal and totals are recomputed after the update.
    """
    update_data = item_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update data provided",
        )

    booking = session.get(Booking, booking_id)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with ID {booking_id} not found",
        )
    item = session.get(BookingItem, item_id)
    if not item or item.booking_id != booking.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking item not found or does not belong to this booking",
        )
    if item.trip_merchandise_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change ticket type for merchandise items",
        )
    if booking.booking_status == BookingStatus.checked_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change ticket type for a checked-in booking",
        )

    new_boat_id = update_data.get("boat_id")
    if new_boat_id is not None and new_boat_id != item.boat_id:
        trip_boats = crud.get_trip_boats_by_trip(
            session=session, trip_id=item.trip_id, limit=100
        )
        boat_ids_on_trip = {tb.boat_id for tb in trip_boats}
        if new_boat_id not in boat_ids_on_trip:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target boat is not on this trip",
            )

    effective_boat_id = new_boat_id if new_boat_id is not None else item.boat_id
    new_item_type = update_data.get("item_type")
    effective_item_type = new_item_type if new_item_type is not None else item.item_type

    if new_item_type is not None or new_boat_id is not None:
        effective = crud.get_effective_pricing(
            session=session,
            trip_id=item.trip_id,
            boat_id=effective_boat_id,
        )
        by_type = {p.ticket_type: p for p in effective}
        if effective_item_type not in by_type:
            boat = session.get(Boat, effective_boat_id)
            boat_name = boat.name if boat else str(effective_boat_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ticket type '{effective_item_type}' is not available for boat '{boat_name}'. Change ticket type or choose another boat.",
            )
        pricing = by_type[effective_item_type]
        capacities = crud.get_effective_capacity_per_ticket_type(
            session=session,
            trip_id=item.trip_id,
            boat_id=effective_boat_id,
        )
        cap = capacities.get(effective_item_type)
        if cap is not None:
            paid = crud.get_paid_ticket_count_per_boat_per_item_type_for_trip(
                session=session, trip_id=item.trip_id
            ).get((effective_boat_id, effective_item_type), 0)
            extra = (
                item.quantity
                if (
                    effective_item_type != item.item_type
                    or effective_boat_id != item.boat_id
                )
                else 0
            )
            total_after = paid + extra
            if total_after > cap:
                boat = session.get(Boat, effective_boat_id)
                boat_name = boat.name if boat else str(effective_boat_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Boat '{boat_name}' capacity for '{effective_item_type}' would be exceeded",
                )
        update_data["price_per_unit"] = pricing.price
        if new_item_type is not None:
            update_data["item_type"] = new_item_type
        if new_boat_id is not None:
            update_data["boat_id"] = new_boat_id

    crud.update_booking_item(
        session=session, db_obj=item, obj_in=BookingItemUpdate(**update_data)
    )

    items = get_booking_items_in_display_order(session, booking.id)
    new_subtotal = sum(i.price_per_unit * i.quantity for i in items)
    booking.subtotal = new_subtotal
    trip = session.get(Trip, items[0].trip_id) if items else None
    if trip:
        mission = session.get(Mission, trip.mission_id)
        launch = session.get(Launch, mission.launch_id) if mission else None
        tax_rate = None
        if launch is not None:
            jurisdictions = crud.get_jurisdictions_by_location(
                session=session, location_id=launch.location_id, limit=1
            )
            if jurisdictions:
                tax_rate = jurisdictions[0].sales_tax_rate
        if tax_rate is not None:
            new_tax, new_total = compute_booking_totals(
                new_subtotal,
                booking.discount_amount,
                tax_rate,
                booking.tip_amount,
            )
            booking.tax_amount = new_tax
            booking.total_amount = new_total
    session.add(booking)
    session.commit()
    session.refresh(booking)

    updated_items = get_booking_items_in_display_order(session, booking.id)
    booking_public = BookingPublic.model_validate(booking)
    booking_public.items = [BookingItemPublic.model_validate(i) for i in updated_items]
    return booking_public


@router.post(
    "/id/{booking_id}/reschedule",
    response_model=BookingPublic,
    dependencies=[Depends(deps.get_current_active_superuser)],
    operation_id="bookings_reschedule",
)
def reschedule_booking(
    *,
    session: Session = Depends(deps.get_db),
    booking_id: uuid.UUID,
    body: RescheduleBookingRequest,
) -> BookingPublic:
    """
    Move all ticket items for this booking to another trip (same mission).

    Merchandise items are left on their current trips. Target trip must be
    active, not departed, and have capacity for the moved quantities.
    """
    booking = session.get(Booking, booking_id)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with ID {booking_id} not found",
        )
    if booking.booking_status == BookingStatus.checked_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reschedule a checked-in booking",
        )

    items = get_booking_items_in_display_order(session, booking.id)
    ticket_items = [i for i in items if i.trip_merchandise_id is None]
    if not ticket_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking has no ticket items to reschedule",
        )

    target_trip = session.get(Trip, body.target_trip_id)
    if not target_trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip {body.target_trip_id} not found",
        )
    if not target_trip.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target trip is not active",
        )
    first_trip = session.get(Trip, ticket_items[0].trip_id)
    if not first_trip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking item trip not found",
        )
    if target_trip.mission_id != first_trip.mission_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target trip must belong to the same mission as the booking",
        )

    trip_boats = crud.get_trip_boats_by_trip(
        session=session, trip_id=body.target_trip_id
    )
    if not trip_boats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target trip has no boats",
        )
    if len(trip_boats) == 1:
        target_boat_id = trip_boats[0].boat_id
    else:
        if body.boat_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target trip has multiple boats; boat_id is required",
            )
        boat_ids = {tb.boat_id for tb in trip_boats}
        if body.boat_id not in boat_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="boat_id is not associated with the target trip",
            )
        target_boat_id = body.boat_id

    capacities = crud.get_effective_capacity_per_ticket_type(
        session=session,
        trip_id=body.target_trip_id,
        boat_id=target_boat_id,
    )
    paid = crud.get_paid_ticket_count_per_boat_per_item_type_for_trip(
        session=session, trip_id=body.target_trip_id
    )
    this_booking_by_type: dict[str, int] = defaultdict(int)
    for item in ticket_items:
        this_booking_by_type[item.item_type] += item.quantity

    for item_type, qty in this_booking_by_type.items():
        cap = capacities.get(item_type)
        if cap is None and item_type not in capacities:
            boat = session.get(Boat, target_boat_id)
            boat_name = boat.name if boat else str(target_boat_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No capacity for ticket type '{item_type}' on boat '{boat_name}'",
            )
        if cap is not None:
            existing = paid.get((target_boat_id, item_type), 0)
            if existing + qty > cap:
                boat = session.get(Boat, target_boat_id)
                boat_name = boat.name if boat else str(target_boat_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Boat '{boat_name}' capacity for '{item_type}' would be exceeded",
                )

    paid_total = sum(v for (bid, _), v in paid.items() if bid == target_boat_id)
    this_booking_total = sum(this_booking_by_type.values())
    trip_boat = next(
        (tb for tb in trip_boats if tb.boat_id == target_boat_id),
        None,
    )
    if trip_boat:
        boat = session.get(Boat, target_boat_id)
        effective_max = (
            trip_boat.max_capacity
            if trip_boat.max_capacity is not None
            else (boat.capacity if boat else 0)
        )
        if paid_total + this_booking_total > effective_max:
            boat = session.get(Boat, target_boat_id)
            boat_name = boat.name if boat else str(target_boat_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Boat '{boat_name}' has {effective_max} total seat(s) "
                    f"with {paid_total} already booked; rescheduling {this_booking_total} ticket(s) "
                    f"would exceed capacity"
                ),
            )

    for item in ticket_items:
        item.trip_id = body.target_trip_id
        item.boat_id = target_boat_id
        session.add(item)

    session.commit()
    session.refresh(booking)
    updated_items = get_booking_items_in_display_order(session, booking.id)
    booking_public = BookingPublic.model_validate(booking)
    booking_public.items = [
        BookingItemPublic.model_validate(item) for item in updated_items
    ]
    logger.info(
        f"Rescheduled booking {booking_id} ticket items to trip {body.target_trip_id}"
    )
    return booking_public


@router.post(
    "/check-in/{confirmation_code}",
    response_model=BookingPublic,
    dependencies=[Depends(deps.get_current_active_superuser)],
)
def check_in_booking(
    *,
    session: Session = Depends(deps.get_db),
    confirmation_code: str,
    trip_id: str | None = None,
    boat_id: str | None = None,
) -> BookingPublic:
    """
    Check in a booking by confirmation code.

    Validates the booking against the selected trip/boat context and updates
    the booking status to 'checked_in' and item statuses to 'fulfilled'.
    """
    try:
        # Validate confirmation code format
        validate_confirmation_code(confirmation_code)

        # Fetch booking with items
        booking = session.exec(
            select(Booking).where(Booking.confirmation_code == confirmation_code)
        ).first()

        if not booking:
            logger.warning(
                f"Booking not found for confirmation code: {confirmation_code}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found with the provided confirmation code",
            )

        # Validate booking status
        if booking.booking_status not in [
            BookingStatus.confirmed,
            BookingStatus.checked_in,
        ]:
            logger.warning(
                f"Invalid booking status for check-in: {booking.booking_status} (confirmation: {confirmation_code})"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot check in booking with status '{booking.booking_status}'. Booking must be 'confirmed'.",
            )

        # If trip_id and boat_id are provided, validate against booking items
        if trip_id and boat_id:
            # Find matching booking item
            matching_item = session.exec(
                select(BookingItem).where(
                    (BookingItem.booking_id == booking.id)
                    & (BookingItem.trip_id == trip_id)
                    & (BookingItem.boat_id == boat_id)
                )
            ).first()

            if not matching_item:
                logger.warning(
                    f"No matching booking item found for trip {trip_id} and boat {boat_id} "
                    f"in booking {confirmation_code}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Booking does not contain items for the specified trip and boat combination",
                )

        # Update booking status to checked_in
        booking.booking_status = BookingStatus.checked_in
        session.add(booking)

        # Update all booking items to fulfilled status and variation quantity_fulfilled
        items = session.exec(
            select(BookingItem).where(BookingItem.booking_id == booking.id)
        ).all()

        for item in items:
            item.status = BookingItemStatus.fulfilled
            session.add(item)
            if item.merchandise_variation_id:
                variation = session.get(
                    MerchandiseVariation, item.merchandise_variation_id
                )
                if variation:
                    variation.quantity_fulfilled += item.quantity
                    session.add(variation)

        # Commit all changes
        session.commit()
        session.refresh(booking)

        updated_items = get_booking_items_in_display_order(session, booking.id)
        booking_public = BookingPublic.model_validate(booking)
        booking_public.items = [
            BookingItemPublic.model_validate(item) for item in updated_items
        ]

        logger.info(f"Successfully checked in booking {confirmation_code}")
        return booking_public

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        session.rollback()
        logger.exception(
            f"Unexpected error during check-in for {confirmation_code}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during check-in. Please try again later.",
        )


@router.post(
    "/revert-check-in/{confirmation_code}",
    response_model=BookingPublic,
    dependencies=[Depends(deps.get_current_active_superuser)],
    operation_id="bookings_revert_check_in",
)
def revert_check_in(
    *,
    session: Session = Depends(deps.get_db),
    confirmation_code: str,
) -> BookingPublic:
    """
    Revert a checked-in booking back to confirmed.

    Allowed only when booking status is checked_in. Sets booking status to
    confirmed and all booking items back to active.
    """
    try:
        validate_confirmation_code(confirmation_code)

        booking = session.exec(
            select(Booking).where(Booking.confirmation_code == confirmation_code)
        ).first()

        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found with the provided confirmation code",
            )

        if booking.booking_status != BookingStatus.checked_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot revert check-in: booking status is '{booking.booking_status}', not 'checked_in'.",
            )

        booking.booking_status = BookingStatus.confirmed
        session.add(booking)

        items = session.exec(
            select(BookingItem).where(BookingItem.booking_id == booking.id)
        ).all()
        for item in items:
            item.status = BookingItemStatus.active
            session.add(item)
            if item.merchandise_variation_id:
                variation = session.get(
                    MerchandiseVariation, item.merchandise_variation_id
                )
                if variation:
                    variation.quantity_fulfilled -= item.quantity
                    variation.quantity_fulfilled = max(0, variation.quantity_fulfilled)
                    session.add(variation)

        session.commit()
        session.refresh(booking)

        updated_items = get_booking_items_in_display_order(session, booking.id)
        booking_public = BookingPublic.model_validate(booking)
        booking_public.items = [
            BookingItemPublic.model_validate(item) for item in updated_items
        ]

        logger.info(f"Reverted check-in for booking {confirmation_code}")
        return booking_public

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception(
            f"Unexpected error reverting check-in for {confirmation_code}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later.",
        )


@router.post(
    "/{confirmation_code}/resend-email",
    operation_id="bookings_resend_booking_confirmation_email",
)
def resend_booking_confirmation_email(
    *,
    session: Session = Depends(deps.get_db),
    confirmation_code: str,
) -> dict:
    """
    Resend booking confirmation email.

    Available for both admin and public use.

    Args:
        confirmation_code: The booking confirmation code

    Returns:
        dict: Status of the email sending
    """
    try:
        # Validate confirmation code format
        validate_confirmation_code(confirmation_code)

        # Get booking with items
        booking = get_booking_with_items(
            session, confirmation_code, include_qr_generation=False
        )

        # Only send emails for confirmed bookings
        if booking.booking_status not in [
            BookingStatus.confirmed,
            BookingStatus.checked_in,
            BookingStatus.completed,
        ]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only resend emails for confirmed bookings",
            )

        # Check if emails are enabled
        if not settings.emails_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Email service is not available",
            )

        # Get mission name, booking items, and experience display for email
        mission_name = get_mission_name_for_booking(session, booking)
        booking_items = prepare_booking_items_for_email(booking)
        items = get_booking_items_in_display_order(session, booking.id)
        experience_display = (
            build_experience_display_dict(session, items) if items else None
        )
        qr_code_base64 = booking.qr_code_base64 or generate_qr_code(
            booking.confirmation_code
        )

        # Generate and send the email
        email_data = generate_booking_confirmation_email(
            email_to=booking.user_email,
            user_name=f"{booking.first_name} {booking.last_name}".strip(),
            confirmation_code=booking.confirmation_code,
            mission_name=mission_name,
            booking_items=booking_items,
            total_amount=booking.total_amount / 100.0,  # cents to dollars for display
            qr_code_base64=qr_code_base64,
            experience_display=experience_display,
        )

        send_email(
            email_to=booking.user_email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )

        return {"status": "success", "message": "Confirmation email sent successfully"}

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log the error and return a generic error response
        logger.error(
            f"Failed to resend booking confirmation email for {confirmation_code}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send confirmation email. Please try again later.",
        )


@router.post(
    "/refund/{confirmation_code}",
    response_model=BookingPublic,
    dependencies=[Depends(deps.get_current_active_superuser)],
)
def process_refund(
    confirmation_code: str,
    body: RefundRequest,
    *,
    session: Session = Depends(deps.get_db),
) -> BookingPublic:
    """
    Process a refund for a booking.

    refund_amount_cents: Amount to refund in cents. If None, refunds full booking total.
    Validates the booking and processes the refund through Stripe,
    then updates the booking status to 'refunded'.
    """
    refund_reason = body.refund_reason
    refund_notes = body.refund_notes
    refund_amount_cents = body.refund_amount_cents
    try:
        # Validate confirmation code format
        validate_confirmation_code(confirmation_code)

        # Fetch booking with items
        booking = session.exec(
            select(Booking).where(Booking.confirmation_code == confirmation_code)
        ).first()

        if not booking:
            logger.warning(
                f"Booking not found for confirmation code: {confirmation_code}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found with the provided confirmation code",
            )

        # Validate booking status (cancelled/refunded = terminal; allow confirmed/checked_in/completed)
        if booking.booking_status not in [
            BookingStatus.confirmed,
            BookingStatus.checked_in,
            BookingStatus.completed,
        ]:
            logger.warning(
                f"Invalid booking status for refund: {booking.booking_status} (confirmation: {confirmation_code})"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot refund booking with status '{booking.booking_status}'. Booking must be 'confirmed', 'checked_in', or 'completed'.",
            )

        refunded_so_far = getattr(booking, "refunded_amount_cents", 0) or 0
        remaining_refundable = booking.total_amount - refunded_so_far
        if remaining_refundable <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No remaining amount to refund for this booking.",
            )

        # Validate refund amount (all in cents)
        amount_to_refund = (
            refund_amount_cents
            if refund_amount_cents is not None
            else remaining_refundable
        )
        if amount_to_refund > remaining_refundable:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Refund amount cannot exceed remaining refundable amount (${remaining_refundable / 100:.2f}).",
            )
        if amount_to_refund <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Refund amount must be positive.",
            )

        logger.info(
            f"process_refund received reason={refund_reason!r} notes={refund_notes!r} "
            f"for booking {confirmation_code}"
        )

        # Process Stripe refund if payment intent exists
        if booking.payment_intent_id:
            try:
                from app.core.stripe import refund_payment

                stripe_amount = amount_to_refund  # already cents
                refund = refund_payment(booking.payment_intent_id, stripe_amount)

                logger.info(
                    f"Stripe refund processed: {refund.id} for booking {confirmation_code}"
                )
            except Exception as e:
                logger.error(
                    f"Stripe refund failed for booking {confirmation_code}: {str(e)}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to process Stripe refund: {str(e)}",
                )
        else:
            logger.warning(
                f"No payment intent found for booking {confirmation_code}, processing refund without Stripe"
            )

        # Update cumulative refund and store reason/notes at booking level (for display)
        booking.refunded_amount_cents = refunded_so_far + amount_to_refund
        booking.refund_reason = refund_reason
        booking.refund_notes = refund_notes
        session.add(booking)

        items = session.exec(
            select(BookingItem).where(BookingItem.booking_id == booking.id)
        ).all()

        # Always store refund reason and notes on all items (for display in booking details)
        for item in items:
            item.refund_reason = refund_reason
            item.refund_notes = refund_notes
            session.add(item)

        if booking.refunded_amount_cents >= booking.total_amount:
            booking.booking_status = BookingStatus.cancelled
            booking.payment_status = PaymentStatus.refunded
            for item in items:
                was_fulfilled = item.status == BookingItemStatus.fulfilled
                item.status = BookingItemStatus.refunded
                session.add(item)
                # Return inventory to variation: decrement quantity_sold and, if was fulfilled, quantity_fulfilled
                if item.merchandise_variation_id:
                    variation = session.get(
                        MerchandiseVariation, item.merchandise_variation_id
                    )
                    if variation:
                        variation.quantity_sold -= item.quantity
                        variation.quantity_sold = max(0, variation.quantity_sold)
                        if was_fulfilled:
                            variation.quantity_fulfilled -= item.quantity
                            variation.quantity_fulfilled = max(
                                0, variation.quantity_fulfilled
                            )
                        session.add(variation)
        else:
            # Partial refund: keep booking_status (confirmed/checked_in/completed); only payment is partially_refunded
            booking.payment_status = PaymentStatus.partially_refunded

        # Commit all changes
        session.commit()
        session.refresh(booking)

        # Log first item so we can confirm reason/notes were persisted (debug)
        first_item = session.exec(
            select(BookingItem).where(BookingItem.booking_id == booking.id)
        ).first()
        if first_item:
            logger.info(
                f"process_refund after commit item refund_reason={first_item.refund_reason!r} "
                f"refund_notes={first_item.refund_notes!r}"
            )

        # Send refund confirmation email
        try:
            from app.utils import generate_booking_refunded_email

            # Get mission name
            mission = session.get(Mission, booking.mission_id)
            mission_name = mission.name if mission else "Unknown Mission"

            email_data = generate_booking_refunded_email(
                email_to=booking.user_email,
                user_name=f"{booking.first_name} {booking.last_name}".strip(),
                confirmation_code=booking.confirmation_code,
                mission_name=mission_name,
                refund_amount=amount_to_refund / 100.0,  # cents to dollars for display
            )

            send_email(
                email_to=booking.user_email,
                subject=email_data.subject,
                html_content=email_data.html_content,
            )

            logger.info(f"Refund confirmation email sent to {booking.user_email}")
        except Exception as e:
            logger.error(
                f"Failed to send refund email for booking {confirmation_code}: {str(e)}"
            )
            # Don't fail the refund if email sending fails

        updated_items = get_booking_items_in_display_order(session, booking.id)
        booking_public = BookingPublic.model_validate(booking)
        booking_public.items = [
            BookingItemPublic.model_validate(item) for item in updated_items
        ]

        logger.info(f"Successfully processed refund for booking {confirmation_code}")
        return booking_public

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        session.rollback()
        logger.exception(
            f"Unexpected error during refund processing for {confirmation_code}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during refund processing. Please try again later.",
        )


@router.get(
    "/export/csv",
    dependencies=[Depends(deps.get_current_active_superuser)],
)
def export_bookings_csv(
    *,
    session: Session = Depends(deps.get_db),
    mission_id: str | None = None,
    trip_id: str | None = None,
    boat_id: str | None = None,
    booking_status: str | None = None,
    fields: str | None = None,  # Comma-separated list of field names
) -> Response:
    """
    Export bookings data to CSV format.

    Supports filtering by mission_id, trip_id, boat_id, and booking_status.
    Supports field selection via the fields parameter (comma-separated list of field names).
    Available fields: confirmation_code, customer_name, email, phone, billing_address,
    booking_status, payment_status, total_amount, subtotal, discount_amount, tax_amount, tip_amount, created_at,
    trip_type, boat_name; ticket_types (or ticket_types_quantity, ticket_types_price,
    ticket_types_total); swag (or swag_description, swag_total).

    When ticket-type columns are requested (ticket_types, ticket_types_quantity, etc.),
    trip_id should be provided. The ticket-type columns will be derived from that trip's
    effective pricing (BoatPricing + TripBoatPricing across boats on the trip).
    Booking items will be matched to the trip's ticket types (with backward compatibility
    for legacy naming variants like "adult" vs "adult_ticket").
    """
    try:
        import csv
        import io

        from fastapi.responses import Response

        # Build query
        query = select(Booking)

        # Apply filters
        conditions = []

        if mission_id or trip_id or boat_id:
            # Join with BookingItem if we need to filter by mission, trip, or boat
            query = query.join(BookingItem)

            if mission_id:
                conditions.append(BookingItem.trip.has(Trip.mission_id == mission_id))
            if trip_id:
                conditions.append(BookingItem.trip_id == trip_id)
            if boat_id:
                try:
                    conditions.append(BookingItem.boat_id == uuid.UUID(boat_id))
                except (ValueError, TypeError):
                    pass

        if booking_status:
            conditions.append(Booking.booking_status == booking_status)

        # Apply all conditions
        if conditions:
            query = query.where(*conditions)

        # Execute query
        bookings = session.exec(query).all()

        # Check if ticket-type columns are requested
        will_include_ticket_types = (
            fields
            and any(
                f in fields.split(",")
                for f in [
                    "ticket_types",
                    "ticket_types_quantity",
                    "ticket_types_price",
                    "ticket_types_total",
                ]
            )
            or (not fields)
        )  # Default includes ticket_types

        # Determine ticket types: from effective pricing if trip_id (and optionally boat_id) provided, else from booking items
        if trip_id and will_include_ticket_types:
            if boat_id:
                try:
                    trip_uuid = uuid.UUID(trip_id)
                    boat_uuid = uuid.UUID(boat_id)
                except (ValueError, TypeError):
                    trip_uuid = boat_uuid = None
                if trip_uuid and boat_uuid:
                    pricing = crud.get_effective_pricing(
                        session=session,
                        trip_id=trip_uuid,
                        boat_id=boat_uuid,
                    )
                    sorted_ticket_types = [p.ticket_type for p in pricing]
                else:
                    sorted_ticket_types = crud.get_effective_ticket_types_for_trip(
                        session=session, trip_id=uuid.UUID(trip_id)
                    )
            else:
                sorted_ticket_types = crud.get_effective_ticket_types_for_trip(
                    session=session, trip_id=uuid.UUID(trip_id)
                )
        else:
            # Fallback: collect from booking items (for exports without trip selection)
            def normalize_ticket_type(raw: str) -> str:
                """Normalize ticket type names: remove '_ticket' suffix to merge legacy variants."""
                if raw.endswith("_ticket"):
                    return raw[:-7]
                return raw

            all_ticket_types: set[str] = set()
            for booking in bookings:
                items = session.exec(
                    select(BookingItem).where(BookingItem.booking_id == booking.id)
                ).all()
                for item in items:
                    if item.trip_merchandise_id is None:
                        all_ticket_types.add(normalize_ticket_type(item.item_type))
            sorted_ticket_types = sorted(all_ticket_types)

        def match_item_to_ticket_type(
            item_type: str, trip_ticket_types: list[str]
        ) -> str | None:
            """Match booking item_type to a trip's ticket type (with backward compatibility).

            Returns the matching trip ticket_type, or None if no match.
            """
            # Direct match
            if item_type in trip_ticket_types:
                return item_type
            # Try with _ticket suffix removed (legacy: item_type="adult" matches trip_ticket_type="adult_ticket")
            if item_type.endswith("_ticket"):
                base = item_type[:-7]
                if base in trip_ticket_types:
                    return base
            # Try adding _ticket suffix (legacy: item_type="adult" matches trip_ticket_type="adult_ticket")
            with_suffix = f"{item_type}_ticket"
            if with_suffix in trip_ticket_types:
                return with_suffix
            return None

        # Define all available fields
        base_fields = {
            "confirmation_code": "Confirmation Code",
            "customer_name": "Customer Name",
            "email": "Email",
            "phone": "Phone",
            "billing_address": "Billing Address",
            "status": "Status",
            "total_amount": "Total Amount",
            "subtotal": "Subtotal",
            "discount_amount": "Discount Amount",
            "tax_amount": "Tax Amount",
            "tip_amount": "Tip Amount",
            "created_at": "Created At",
            "trip_type": "Trip Type",
            "boat_name": "Boat Name",
        }

        # Parse fields parameter
        selected_fields: list[str] = []
        if fields:
            selected_fields = [f.strip() for f in fields.split(",") if f.strip()]
        else:
            # If no fields specified, include all fields
            selected_fields = list(base_fields.keys()) + ["ticket_types", "swag"]

        # Validate selected fields; support granular ticket_types and swag
        valid_fields = set(base_fields.keys()) | {
            "ticket_types",
            "ticket_types_quantity",
            "ticket_types_price",
            "ticket_types_total",
            "swag",
            "swag_description",
            "swag_total",
        }
        selected_fields = [f for f in selected_fields if f in valid_fields]

        # If no valid fields selected, use all fields
        if not selected_fields:
            selected_fields = list(base_fields.keys()) + ["ticket_types", "swag"]

        # When boat is specified, boat name column is redundant (same boat for all rows)
        if boat_id:
            selected_fields = [f for f in selected_fields if f != "boat_name"]

        # Which ticket/swag sub-columns to include
        include_ticket_quantity = (
            "ticket_types" in selected_fields
            or "ticket_types_quantity" in selected_fields
        )
        include_ticket_price = (
            "ticket_types" in selected_fields or "ticket_types_price" in selected_fields
        )
        include_ticket_total = (
            "ticket_types" in selected_fields or "ticket_types_total" in selected_fields
        )
        include_swag_description = (
            "swag" in selected_fields or "swag_description" in selected_fields
        )
        include_swag_total = (
            "swag" in selected_fields or "swag_total" in selected_fields
        )

        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)

        # Build header: base fields in order, then ticket columns, then swag
        header = []
        for field_key in selected_fields:
            if field_key in base_fields:
                header.append(base_fields[field_key])
        if include_ticket_quantity or include_ticket_price or include_ticket_total:
            for ticket_type in sorted_ticket_types:
                if include_ticket_quantity:
                    header.append(f"{ticket_type} Quantity")
                if include_ticket_price:
                    header.append(f"{ticket_type} Price")
                if include_ticket_total:
                    header.append(f"{ticket_type} Total")
        if include_swag_description:
            header.append("Swag Description")
        if include_swag_total:
            header.append("Swag Total")

        writer.writerow(header)

        # Write booking data - one row per booking
        for booking in bookings:
            # Get booking items (filter by trip_id and boat_id when provided)
            item_query = select(BookingItem).where(BookingItem.booking_id == booking.id)
            if trip_id:
                item_query = item_query.where(BookingItem.trip_id == trip_id)
            if boat_id:
                try:
                    boat_uuid = uuid.UUID(boat_id)
                    item_query = item_query.where(BookingItem.boat_id == boat_uuid)
                except (ValueError, TypeError):
                    pass
            items = session.exec(item_query).all()

            # Aggregate items by type
            tickets: dict[
                str, dict[str, int]
            ] = {}  # ticket_type -> {qty, price (cents)}
            swag_items: list[str] = []
            swag_total = 0.0

            trip_type = ""
            boat_name = ""

            for item in items:
                # Get trip and boat info from first item
                if not trip_type:
                    trip = session.get(Trip, item.trip_id)
                    if trip:
                        trip_type = trip.type
                if not boat_name:
                    boat = session.get(Boat, item.boat_id)
                    if boat:
                        boat_name = boat.name

                # Group items by type
                # Merchandise items have trip_merchandise_id set
                if item.trip_merchandise_id:
                    # Merchandise item - item_type contains the merchandise name
                    merch_name = item.item_type
                    if item.variant_option:
                        merch_name = f"{merch_name} – {item.variant_option}"
                    swag_items.append(
                        f"{merch_name} x{item.quantity}"
                        if item.quantity > 1
                        else merch_name
                    )
                    swag_total += item.price_per_unit * item.quantity
                else:
                    # Ticket item - match to trip's ticket types if trip_id provided
                    if trip_id and will_include_ticket_types:
                        # Match item_type to trip's ticket type (with backward compatibility)
                        matched_type = match_item_to_ticket_type(
                            item.item_type, sorted_ticket_types
                        )
                        if matched_type:
                            if matched_type not in tickets:
                                tickets[matched_type] = {
                                    "qty": 0,
                                    "price": 0,
                                }  # price in cents
                            tickets[matched_type]["qty"] += item.quantity
                            tickets[matched_type]["price"] += (
                                item.price_per_unit * item.quantity
                            )
                    else:
                        # Fallback: normalize for exports without trip selection
                        def normalize_ticket_type(raw: str) -> str:
                            if raw.endswith("_ticket"):
                                return raw[:-7]
                            return raw

                        normalized_type = normalize_ticket_type(item.item_type)
                        if normalized_type not in tickets:
                            tickets[normalized_type] = {
                                "qty": 0,
                                "price": 0,
                            }  # price in cents
                        tickets[normalized_type]["qty"] += item.quantity
                        tickets[normalized_type]["price"] += (
                            item.price_per_unit * item.quantity
                        )

            # Build row data based on selected fields (amounts in dollars for CSV display)
            row = []
            field_data = {
                "confirmation_code": booking.confirmation_code,
                "customer_name": f"{booking.first_name} {booking.last_name}".strip(),
                "email": booking.user_email,
                "phone": booking.user_phone,
                "billing_address": booking.billing_address,
                "booking_status": booking.booking_status,
                "payment_status": booking.payment_status,
                "total_amount": round(booking.total_amount / 100, 2),
                "subtotal": round(booking.subtotal / 100, 2),
                "discount_amount": round(booking.discount_amount / 100, 2),
                "tax_amount": round(booking.tax_amount / 100, 2),
                "tip_amount": round(booking.tip_amount / 100, 2),
                "created_at": booking.created_at.isoformat(),
                "trip_type": trip_type,
                "boat_name": boat_name,
            }

            # Base fields in selected order
            for field_key in selected_fields:
                if field_key in field_data:
                    row.append(field_data[field_key])
            # Ticket columns (same order as header)
            if include_ticket_quantity or include_ticket_price or include_ticket_total:
                for ticket_type in sorted_ticket_types:
                    if ticket_type in tickets:
                        data = tickets[ticket_type]
                        if include_ticket_quantity:
                            row.append(data["qty"])
                        if include_ticket_price:
                            row.append(
                                f"{data['price'] / data['qty'] / 100:.2f}"
                                if data["qty"] > 0
                                else "0.00"
                            )
                        if include_ticket_total:
                            row.append(f"{data['price'] / 100:.2f}")
                    else:
                        if include_ticket_quantity:
                            row.append("")
                        if include_ticket_price:
                            row.append("")
                        if include_ticket_total:
                            row.append("")
            # Swag columns
            if include_swag_description:
                row.append(", ".join(swag_items) if swag_items else "")
            if include_swag_total:
                row.append(f"{swag_total / 100:.2f}" if swag_total else "")

            writer.writerow(row)

        # Get CSV content
        csv_content = output.getvalue()
        output.close()

        # Create response
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=bookings_export.csv"},
        )

    except Exception as e:
        logger.exception(f"Error exporting bookings CSV: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while exporting data. Please try again later.",
        )
