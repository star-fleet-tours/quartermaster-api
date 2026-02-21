import enum
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import EmailStr, field_serializer, field_validator
from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.core.constants import VALID_US_STATES


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=64)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalize email to lowercase for case-insensitive handling."""
        if v:
            return v.lower()
        return v

    @field_validator("full_name", mode="before")
    @classmethod
    def validate_full_name(cls, v: str | None) -> str | None:
        """Validate full_name: max 64 chars, letters, numbers, spaces, hyphens, apostrophes; no double quotes."""
        if v is None:
            return v
        if len(v) > 64:
            raise ValueError("Full name must be 64 characters or less")
        if '"' in v:
            raise ValueError(
                "Full name cannot contain double quotes. Letters (including accented), numbers, spaces, hyphens, and apostrophes are allowed."
            )
        if not re.match(r"^[\w\s\-']+$", v, re.UNICODE):
            raise ValueError(
                "Full name can only contain letters (including accented), numbers, spaces, hyphens, and apostrophes"
            )
        return v


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=40)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=40)
    full_name: str | None = Field(default=None, max_length=64)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalize email to lowercase for case-insensitive handling."""
        if v:
            return v.lower()
        return v

    @field_validator("full_name", mode="before")
    @classmethod
    def validate_full_name(cls, v: str | None) -> str | None:
        """Validate full_name: max 64 chars, letters, numbers, spaces, hyphens, apostrophes; no double quotes."""
        if v is None:
            return v
        if len(v) > 64:
            raise ValueError("Full name must be 64 characters or less")
        if '"' in v:
            raise ValueError(
                "Full name cannot contain double quotes. Letters (including accented), numbers, spaces, hyphens, and apostrophes are allowed."
            )
        if not re.match(r"^[\w\s\-']+$", v, re.UNICODE):
            raise ValueError(
                "Full name can only contain letters (including accented), numbers, spaces, hyphens, and apostrophes"
            )
        return v


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=40)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = Field(default=None, max_length=255)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        """Normalize email to lowercase for case-insensitive handling."""
        if v:
            return v.lower()
        return v

    @field_validator("full_name", mode="before")
    @classmethod
    def validate_full_name(cls, v: str | None) -> str | None:
        """Validate full_name: max 64 chars, letters, numbers, spaces, hyphens, apostrophes; no double quotes."""
        if v is None:
            return v
        if len(v) > 64:
            raise ValueError("Full name must be 64 characters or less")
        if '"' in v:
            raise ValueError(
                "Full name cannot contain double quotes. Letters (including accented), numbers, spaces, hyphens, and apostrophes are allowed."
            )
        if not re.match(r"^[\w\s\-']+$", v, re.UNICODE):
            raise ValueError(
                "Full name can only contain letters (including accented), numbers, spaces, hyphens, and apostrophes"
            )
        return v


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=40)
    new_password: str = Field(min_length=8, max_length=40)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=40)


# Location models
class LocationBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    state: str = Field(min_length=2, max_length=2)
    timezone: str = Field(default="UTC", max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Require IANA timezone name (e.g. America/New_York)."""
        try:
            ZoneInfo(v)
        except Exception:
            raise ValueError(
                f"Invalid timezone: {v!r}. Use IANA name (e.g. America/New_York)."
            )
        return v

    @field_validator("state")
    def validate_state(cls, v):
        if v.upper() not in VALID_US_STATES:
            raise ValueError(
                f"Invalid state code. Must be one of {', '.join(VALID_US_STATES)}"
            )
        return v.upper()  # Ensure state is always uppercase


class LocationCreate(LocationBase):
    pass


class LocationUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except Exception:
            raise ValueError(
                f"Invalid timezone: {v!r}. Use IANA name (e.g. America/New_York)."
            )
        return v


class Location(LocationBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )


class LocationPublic(LocationBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class LocationsPublic(SQLModel):
    data: list[LocationPublic]
    count: int


# Jurisdiction models
class JurisdictionBase(SQLModel):
    name: str = Field(index=True, max_length=255)
    sales_tax_rate: float = Field(ge=0.0, le=1.0)
    location_id: uuid.UUID = Field(foreign_key="location.id")


class JurisdictionCreate(SQLModel):
    name: str = Field(index=True, max_length=255)
    sales_tax_rate: float = Field(ge=0.0, le=1.0)
    location_id: uuid.UUID = Field(foreign_key="location.id")


class JurisdictionUpdate(SQLModel):
    name: str | None = Field(default=None, max_length=255)
    sales_tax_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    location_id: uuid.UUID | None = Field(default=None)


class Jurisdiction(JurisdictionBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    # Unidirectional relationship - jurisdiction knows its location but location doesn't track jurisdictions
    location: "Location" = Relationship()


class JurisdictionPublic(JurisdictionBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Include location data for state access
    location: Optional["LocationPublic"] = None


class JurisdictionsPublic(SQLModel):
    data: list[JurisdictionPublic]
    count: int


# Launch models
class LaunchBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    launch_timestamp: datetime
    summary: str = Field(max_length=1000)
    location_id: uuid.UUID = Field(foreign_key="location.id")


class LaunchCreate(LaunchBase):
    pass


class LaunchUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    launch_timestamp: datetime | None = None
    summary: str | None = Field(default=None, max_length=1000)
    location_id: uuid.UUID | None = None


class Launch(LaunchBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    launch_timestamp: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    # Unidirectional relationship - launch knows its location but location doesn't track launches
    location: "Location" = Relationship()


class LaunchPublic(LaunchBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    timezone: str = "UTC"  # IANA name from launch's location; for display

    @field_serializer("launch_timestamp", "created_at", "updated_at")
    def serialize_datetime_utc(self, dt: datetime):
        """Serialize datetimes with Z so clients parse as UTC and display in local time."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class LaunchesPublic(SQLModel):
    data: list[LaunchPublic]
    count: int


# Mission models
class MissionBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    launch_id: uuid.UUID = Field(foreign_key="launch.id")
    active: bool = Field(default=True)
    refund_cutoff_hours: int = Field(default=12, ge=0, le=72)


class MissionCreate(MissionBase):
    pass


class MissionUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    launch_id: uuid.UUID | None = None
    active: bool | None = None
    refund_cutoff_hours: int | None = Field(default=None, ge=0, le=72)


class Mission(MissionBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    # Unidirectional relationship - mission knows its launch but launch doesn't track missions
    launch: "Launch" = Relationship()


class MissionPublic(MissionBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    timezone: str = "UTC"  # IANA name from mission's launch location; for display


class MissionWithStats(MissionPublic):
    trip_count: int = 0
    total_bookings: int = 0
    total_sales: int = 0  # cents (sum of booking.total_amount - booking.tax_amount)


class MissionsPublic(SQLModel):
    data: list[MissionPublic]
    count: int


class MissionsWithStatsPublic(SQLModel):
    data: list[MissionWithStats]
    count: int


# Provider models
class ProviderBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    jurisdiction_id: uuid.UUID = Field(foreign_key="jurisdiction.id")
    map_link: str | None = Field(default=None, max_length=2000)


class ProviderCreate(ProviderBase):
    pass


class ProviderUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    jurisdiction_id: uuid.UUID | None = None
    map_link: str | None = Field(default=None, max_length=2000)


class Provider(ProviderBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    # Unidirectional relationship - provider knows its jurisdiction
    jurisdiction: "Jurisdiction" = Relationship()


class ProviderPublic(ProviderBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Include jurisdiction data for API responses
    jurisdiction: Optional["JurisdictionPublic"] = None


class ProvidersPublic(SQLModel):
    data: list[ProviderPublic]
    count: int


# Boat models
class BoatBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    # Definimos slug como opcional con un valor predeterminado vacío
    slug: str = Field(default="", max_length=255, index=True)
    capacity: int = Field(ge=1)
    provider_id: uuid.UUID = Field(foreign_key="provider.id")


class BoatCreate(BoatBase):
    pass  # El slug se generará en crud.create_boat


class BoatUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    # El slug se generará automáticamente en crud.update_boat si el nombre cambia
    capacity: int | None = Field(default=None, ge=1)
    provider_id: uuid.UUID | None = None


class Boat(BoatBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    # Relationship to provider
    provider: "Provider" = Relationship()
    # Relationship to BoatPricing (boat-level default ticket types/prices)
    pricing: list["BoatPricing"] = Relationship(back_populates="boat")


class BoatPublic(BoatBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Include provider data for API responses
    provider: Optional["ProviderPublic"] = None


class BoatsPublic(SQLModel):
    data: list[BoatPublic]
    count: int


# Trip models
class TripBase(SQLModel):
    mission_id: uuid.UUID = Field(foreign_key="mission.id")
    name: str | None = Field(default=None, max_length=255)  # custom label
    type: str = Field(max_length=50)  # launch_viewing or pre_launch
    active: bool = Field(default=True)
    unlisted: bool = Field(default=False)  # if True, only visible via direct link
    booking_mode: str = Field(
        default="private", max_length=20
    )  # private, early_bird, public
    sales_open_at: datetime | None = None  # trip not bookable until this instant
    check_in_time: datetime
    boarding_time: datetime
    departure_time: datetime


class TripCreate(SQLModel):
    """API request: departure time plus minute offsets; check_in/boarding are computed."""

    mission_id: uuid.UUID = Field(foreign_key="mission.id")
    name: str | None = Field(default=None, max_length=255)
    type: str = Field(max_length=50)  # launch_viewing or pre_launch
    active: bool = Field(default=True)
    unlisted: bool = Field(default=False)
    booking_mode: str = Field(default="private", max_length=20)
    sales_open_at: datetime | None = None
    departure_time: datetime
    boarding_minutes_before_departure: int | None = Field(
        default=None,
        ge=0,
        description="Minutes before departure when boarding starts; default by type",
    )
    checkin_minutes_before_boarding: int | None = Field(
        default=None,
        ge=0,
        description="Minutes before boarding when check-in opens; default by type",
    )


class TripUpdate(SQLModel):
    mission_id: uuid.UUID | None = None
    name: str | None = Field(default=None, max_length=255)
    type: str | None = Field(default=None, max_length=50)
    active: bool | None = None
    unlisted: bool | None = None
    booking_mode: str | None = Field(default=None, max_length=20)
    sales_open_at: datetime | None = None
    departure_time: datetime | None = None
    boarding_minutes_before_departure: int | None = Field(
        default=None, ge=0, description="Minutes before departure when boarding starts"
    )
    checkin_minutes_before_boarding: int | None = Field(
        default=None, ge=0, description="Minutes before boarding when check-in opens"
    )


class Trip(TripBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    sales_open_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    check_in_time: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    boarding_time: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    departure_time: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    # Unidirectional relationship - trip knows its mission but mission doesn't track trips
    mission: "Mission" = Relationship()
    # Relationship to TripBoat
    trip_boats: list["TripBoat"] = Relationship(
        back_populates="trip", sa_relationship_kwargs={"lazy": "joined"}
    )
    # Relationship to TripMerchandise
    merchandise: list["TripMerchandise"] = Relationship(
        back_populates="trip", sa_relationship_kwargs={"lazy": "joined"}
    )


class TripPublic(TripBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    trip_boats: list["TripBoatPublic"] = Field(default_factory=list)
    timezone: str = (
        "UTC"  # IANA name from trip's mission->launch->location; for display
    )
    effective_booking_mode: str = Field(
        default="private",
        description="Booking mode in effect (considering sales_open_at); for display.",
    )

    @field_serializer(
        "sales_open_at",
        "check_in_time",
        "boarding_time",
        "departure_time",
        "created_at",
        "updated_at",
    )
    def serialize_datetime_utc(self, dt: datetime | None):
        """Serialize datetimes with Z so clients parse as UTC and display in local time."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class TripWithStats(TripPublic):
    total_bookings: int = 0
    total_sales: int = 0  # cents (sum of booking.total_amount - booking.tax_amount)


class TripsPublic(SQLModel):
    data: list[TripPublic]
    count: int


class TripsWithStatsPublic(SQLModel):
    data: list[TripWithStats]
    count: int


class PublicTripsResponse(SQLModel):
    """Response for GET /trips/public/ with optional flag for access code prompt."""

    data: list[TripPublic]
    count: int
    all_trips_require_access_code: bool = False


# TripBoat models
class TripBoatBase(SQLModel):
    trip_id: uuid.UUID = Field(foreign_key="trip.id")
    boat_id: uuid.UUID = Field(foreign_key="boat.id")
    max_capacity: int | None = None  # Optional override of boat's standard capacity
    use_only_trip_pricing: bool = Field(
        default=False,
        description="When True, ignore boat defaults; only TripBoatPricing applies.",
    )


class TripBoatCreate(TripBoatBase):
    pass


class TripBoatUpdate(SQLModel):
    trip_id: uuid.UUID | None = None
    boat_id: uuid.UUID | None = None
    max_capacity: int | None = None
    use_only_trip_pricing: bool | None = None


class TripBoat(TripBoatBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    # Relationships
    trip: "Trip" = Relationship(back_populates="trip_boats")
    boat: "Boat" = Relationship()
    # Per-trip, per-boat price overrides (cascade delete when trip boat is removed)
    pricing: list["TripBoatPricing"] = Relationship(
        back_populates="trip_boat", cascade_delete=True
    )


class TripBoatPublic(TripBoatBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    boat: "BoatPublic"


class TripBoatPublicWithAvailability(TripBoatPublic):
    """Trip boat with effective max capacity, remaining slots, and per-ticket-type pricing/availability."""

    max_capacity: int  # Effective capacity (TripBoat.max_capacity or Boat.capacity)
    remaining_capacity: int  # max_capacity minus paid ticket count for this trip/boat
    pricing: list["EffectivePricingItem"] = Field(default_factory=list)
    used_per_ticket_type: dict[str, int] = Field(
        default_factory=dict,
        description="Total ticket count per item_type on this boat (all booking statuses).",
    )


# BoatPricing models (boat-level default ticket types, prices, and capacity per type)
class BoatPricingBase(SQLModel):
    boat_id: uuid.UUID = Field(foreign_key="boat.id")
    ticket_type: str = Field(max_length=32)
    price: int = Field(ge=0)  # cents
    capacity: int = Field(ge=0)  # max seats for this ticket type on this boat


class BoatPricingCreate(BoatPricingBase):
    pass


class BoatPricingUpdate(SQLModel):
    ticket_type: str | None = Field(default=None, max_length=32)
    price: int | None = Field(default=None, ge=0)
    capacity: int | None = Field(default=None, ge=0)


class BoatPricing(BoatPricingBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    boat: "Boat" = Relationship(back_populates="pricing")


class BoatPricingPublic(BoatPricingBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# TripBoatPricing models (per-trip, per-boat price and capacity overrides)
class TripBoatPricingBase(SQLModel):
    trip_boat_id: uuid.UUID = Field(foreign_key="tripboat.id")
    ticket_type: str = Field(max_length=32)
    price: int = Field(ge=0)  # cents
    capacity: int | None = Field(
        default=None, ge=0
    )  # override boat-level capacity for this type


class TripBoatPricingCreate(TripBoatPricingBase):
    pass


class TripBoatPricingUpdate(SQLModel):
    ticket_type: str | None = Field(default=None, max_length=32)
    price: int | None = Field(default=None, ge=0)
    capacity: int | None = Field(default=None, ge=0)


class TripBoatPricing(TripBoatPricingBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    trip_boat: "TripBoat" = Relationship(back_populates="pricing")


class TripBoatPricingPublic(TripBoatPricingBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# Effective pricing for public API (ticket_type + price + capacity + remaining per boat for a trip)
class EffectivePricingItem(SQLModel):
    ticket_type: str
    price: int  # cents
    capacity: int  # max seats for this type on this trip/boat
    remaining: int  # capacity minus paid count for this type


# Merchandise (catalog) models
class MerchandiseBase(SQLModel):
    name: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    price: int = Field(ge=0)  # cents
    quantity_available: int = Field(ge=0)


class MerchandiseCreate(MerchandiseBase):
    pass


class MerchandiseUpdate(SQLModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    price: int | None = Field(default=None, ge=0)  # cents
    quantity_available: int | None = Field(default=None, ge=0)


class Merchandise(MerchandiseBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    variations: list["MerchandiseVariation"] = Relationship(
        back_populates="merchandise"
    )


class MerchandisePublic(MerchandiseBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Computed from variations at read time (not stored)
    variant_name: str | None = None
    variant_options: str | None = None  # comma-separated
    # Populated in list endpoint for admin table (per-variation total, sold, fulfilled)
    variations: list["MerchandiseVariationPublic"] | None = None

    @field_serializer("created_at", "updated_at")
    def serialize_datetime_utc(self, dt: datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


class MerchandisesPublic(SQLModel):
    data: list[MerchandisePublic]
    count: int


# MerchandiseVariation (per-variant inventory: total, sold, fulfilled)
class MerchandiseVariationBase(SQLModel):
    merchandise_id: uuid.UUID = Field(foreign_key="merchandise.id")
    variant_value: str = Field(max_length=128)  # e.g. "M", "S-Red"
    quantity_total: int = Field(ge=0)
    quantity_sold: int = Field(default=0, ge=0)
    quantity_fulfilled: int = Field(default=0, ge=0)


class MerchandiseVariationCreate(SQLModel):
    merchandise_id: uuid.UUID = Field(foreign_key="merchandise.id")
    variant_value: str = Field(max_length=128)
    quantity_total: int = Field(ge=0)
    quantity_sold: int = Field(default=0, ge=0)
    quantity_fulfilled: int = Field(default=0, ge=0)


class MerchandiseVariationUpdate(SQLModel):
    variant_value: str | None = Field(default=None, max_length=128)
    quantity_total: int | None = Field(default=None, ge=0)
    quantity_sold: int | None = Field(default=None, ge=0)
    quantity_fulfilled: int | None = Field(default=None, ge=0)


class MerchandiseVariation(MerchandiseVariationBase, table=True):
    __table_args__ = (
        UniqueConstraint(
            "merchandise_id",
            "variant_value",
            name="uq_merchandisevariation_merchandise_variant",
        ),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    merchandise: "Merchandise" = Relationship(back_populates="variations")


class MerchandiseVariationPublic(SQLModel):
    id: uuid.UUID
    merchandise_id: uuid.UUID
    variant_value: str
    quantity_total: int
    quantity_sold: int
    quantity_fulfilled: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_datetime_utc(self, dt: datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


# TripMerchandise (link trip <-> merchandise with optional overrides)
class TripMerchandiseBase(SQLModel):
    trip_id: uuid.UUID = Field(foreign_key="trip.id")
    merchandise_id: uuid.UUID = Field(foreign_key="merchandise.id")
    quantity_available_override: int | None = Field(default=None, ge=0)
    price_override: int | None = Field(default=None, ge=0)  # cents


class TripMerchandiseCreate(TripMerchandiseBase):
    pass


class TripMerchandiseUpdate(SQLModel):
    quantity_available_override: int | None = Field(default=None, ge=0)
    price_override: int | None = Field(default=None, ge=0)  # cents


class TripMerchandise(TripMerchandiseBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    trip: "Trip" = Relationship(back_populates="merchandise")
    merchandise: "Merchandise" = Relationship()


# Per-variation availability for trip merchandise (for booking form)
class TripMerchandiseVariationAvailability(SQLModel):
    variant_value: str
    quantity_available: int


# Response shape for API: effective name, description, price (cents), quantity_available (from join + overrides)
class TripMerchandisePublic(SQLModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    merchandise_id: uuid.UUID
    name: str
    description: str | None
    price: int  # cents
    quantity_available: int
    variant_name: str | None = None
    variant_options: str | None = None  # comma-separated; frontend splits to list
    # Per-variation quantity available (when merchandise has variations)
    variations_availability: list[TripMerchandiseVariationAvailability] | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_datetime_utc(self, dt: datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()


# --- Booking Mode Enum ---
class BookingMode(str, enum.Enum):
    private = "private"  # Admin only, no public access
    early_bird = "early_bird"  # Requires access code
    public = "public"  # Open to everyone


# --- BookingItem models ---
class BookingItemStatus(str, enum.Enum):
    active = "active"
    refunded = "refunded"
    fulfilled = "fulfilled"


class BookingItemBase(SQLModel):
    booking_id: uuid.UUID = Field(foreign_key="booking.id")
    trip_id: uuid.UUID = Field(foreign_key="trip.id")
    boat_id: uuid.UUID = Field(foreign_key="boat.id")
    # Optional link to a specific trip merchandise item when item_type is merchandise
    trip_merchandise_id: uuid.UUID | None = Field(
        default=None, foreign_key="tripmerchandise.id"
    )
    # Optional link to merchandise variation (for per-variant inventory and fulfillment)
    merchandise_variation_id: uuid.UUID | None = Field(
        default=None, foreign_key="merchandisevariation.id"
    )
    item_type: str = Field(max_length=32)  # e.g. adult_ticket, child_ticket
    quantity: int = Field(ge=1)
    price_per_unit: int = Field(ge=0)  # cents
    status: BookingItemStatus = Field(default=BookingItemStatus.active)
    refund_reason: str | None = Field(default=None, max_length=255)
    refund_notes: str | None = Field(default=None, max_length=1000)
    # Selected variant for merchandise (e.g. "M" when variant_name is "Size")
    variant_option: str | None = Field(default=None, max_length=64)


class BookingItemCreate(SQLModel):
    trip_id: uuid.UUID = Field(foreign_key="trip.id")
    boat_id: uuid.UUID = Field(foreign_key="boat.id")
    trip_merchandise_id: uuid.UUID | None = Field(
        default=None, foreign_key="tripmerchandise.id"
    )
    merchandise_variation_id: uuid.UUID | None = Field(
        default=None, foreign_key="merchandisevariation.id"
    )
    item_type: str = Field(max_length=32)  # e.g. adult_ticket, child_ticket
    quantity: int = Field(ge=1)
    price_per_unit: int = Field(ge=0)  # cents
    status: BookingItemStatus = Field(default=BookingItemStatus.active)
    refund_reason: str | None = Field(default=None, max_length=255)
    refund_notes: str | None = Field(default=None, max_length=1000)
    variant_option: str | None = Field(default=None, max_length=64)


class BookingItemUpdate(SQLModel):
    status: BookingItemStatus | None = None
    refund_reason: str | None = None
    refund_notes: str | None = None
    item_type: str | None = Field(default=None, max_length=32)
    price_per_unit: int | None = Field(default=None, ge=0)
    boat_id: uuid.UUID | None = Field(default=None, foreign_key="boat.id")


class BookingItemQuantityUpdate(SQLModel):
    """Payload to update a single booking item's quantity (draft/pending_payment only). Quantity 0 removes the item."""

    id: uuid.UUID = Field(foreign_key="bookingitem.id")
    quantity: int = Field(ge=0)


class BookingItem(BookingItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    booking: "Booking" = Relationship(back_populates="items")
    trip: "Trip" = Relationship()
    boat: "Boat" = Relationship()


class BookingItemPublic(BookingItemBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --- Booking models ---
class PaymentStatus(str, enum.Enum):
    pending_payment = "pending_payment"
    paid = "paid"
    free = "free"
    failed = "failed"
    refunded = "refunded"
    partially_refunded = "partially_refunded"


class BookingStatus(str, enum.Enum):
    """Booking lifecycle: draft, confirmed, checked_in, completed, cancelled."""

    draft = "draft"
    confirmed = "confirmed"
    checked_in = "checked_in"
    completed = "completed"
    cancelled = "cancelled"


def _validate_name_part(v: str | None, max_length: int = 128) -> str | None:
    """Validate name part (first/last): max chars, letters, numbers, spaces, hyphens, apostrophes; no double quotes."""
    if v is None:
        return v
    if len(v) > max_length:
        raise ValueError(f"Name must be {max_length} characters or less")
    if '"' in v:
        raise ValueError(
            "Name cannot contain double quotes. Letters (including accented), numbers, spaces, hyphens, and apostrophes are allowed."
        )
    if not re.match(r"^[\w\s\-']+$", v, re.UNICODE):
        raise ValueError(
            "Name can only contain letters (including accented), numbers, spaces, hyphens, and apostrophes"
        )
    return v


class BookingBase(SQLModel):
    confirmation_code: str = Field(index=True, unique=True, max_length=32)
    first_name: str = Field(max_length=128)
    last_name: str = Field(max_length=128)

    @field_validator("first_name", mode="before")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        result = _validate_name_part(v, max_length=128)
        assert result is not None
        return result

    @field_validator("last_name", mode="before")
    @classmethod
    def validate_last_name(cls, v: str) -> str:
        result = _validate_name_part(v, max_length=128)
        assert result is not None
        return result

    user_email: str = Field(max_length=255)
    user_phone: str = Field(max_length=40)
    billing_address: str = Field(max_length=1000)
    subtotal: int = Field(ge=0)  # cents
    discount_amount: int = Field(ge=0)  # cents
    tax_amount: int = Field(ge=0)  # cents
    tip_amount: int = Field(ge=0)  # cents
    total_amount: int = Field(ge=0)  # cents
    refunded_amount_cents: int = Field(default=0, ge=0)  # cumulative refunds
    refund_reason: str | None = Field(default=None, max_length=255)
    refund_notes: str | None = Field(default=None, max_length=1000)
    payment_intent_id: str | None = Field(default=None, max_length=255)
    special_requests: str | None = Field(default=None, max_length=1000)
    payment_status: PaymentStatus | None = Field(default=None)
    booking_status: BookingStatus = Field(default=BookingStatus.draft)
    launch_updates_pref: bool = Field(default=False)
    discount_code_id: uuid.UUID | None = Field(
        default=None, foreign_key="discountcode.id"
    )
    admin_notes: str | None = Field(default=None, max_length=2000)


class BookingCreate(SQLModel):
    confirmation_code: str = Field(index=True, unique=True, max_length=32)
    first_name: str = Field(max_length=128)
    last_name: str = Field(max_length=128)
    user_email: str = Field(max_length=255)

    @field_validator("first_name", mode="before")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        result = _validate_name_part(v, max_length=128)
        assert result is not None
        return result

    @field_validator("last_name", mode="before")
    @classmethod
    def validate_last_name(cls, v: str) -> str:
        result = _validate_name_part(v, max_length=128)
        assert result is not None
        return result

    user_phone: str = Field(max_length=40)
    billing_address: str = Field(max_length=1000)
    subtotal: int = Field(ge=0)  # cents
    discount_amount: int = Field(ge=0)  # cents
    tax_amount: int = Field(ge=0)  # cents
    tip_amount: int = Field(ge=0)  # cents
    total_amount: int = Field(ge=0)  # cents
    special_requests: str | None = Field(default=None, max_length=1000)
    launch_updates_pref: bool = Field(default=False)
    discount_code_id: uuid.UUID | None = Field(default=None)
    admin_notes: str | None = Field(default=None, max_length=2000)
    items: list[BookingItemCreate]


class BookingUpdate(SQLModel):
    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    user_email: str | None = Field(default=None, max_length=255)

    @field_validator("first_name", mode="before")
    @classmethod
    def validate_first_name(cls, v: str | None) -> str | None:
        return _validate_name_part(v, max_length=128)

    @field_validator("last_name", mode="before")
    @classmethod
    def validate_last_name(cls, v: str | None) -> str | None:
        return _validate_name_part(v, max_length=128)

    user_phone: str | None = Field(default=None, max_length=40)
    billing_address: str | None = Field(default=None, max_length=1000)
    booking_status: BookingStatus | None = None
    payment_status: PaymentStatus | None = None
    special_requests: str | None = None
    tip_amount: int | None = None  # cents
    discount_amount: int | None = None  # cents
    tax_amount: int | None = None  # cents
    total_amount: int | None = None  # cents
    launch_updates_pref: bool | None = None
    discount_code_id: uuid.UUID | None = None
    item_quantity_updates: list[BookingItemQuantityUpdate] | None = None
    admin_notes: str | None = None


class BookingDraftUpdate(SQLModel):
    """Public PATCH for draft/pending_payment bookings by confirmation code."""

    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    user_email: str | None = Field(default=None, max_length=255)

    @field_validator("first_name", mode="before")
    @classmethod
    def validate_first_name(cls, v: str | None) -> str | None:
        return _validate_name_part(v, max_length=128)

    @field_validator("last_name", mode="before")
    @classmethod
    def validate_last_name(cls, v: str | None) -> str | None:
        return _validate_name_part(v, max_length=128)

    user_phone: str | None = Field(default=None, max_length=40)
    billing_address: str | None = Field(default=None, max_length=1000)
    special_requests: str | None = None
    launch_updates_pref: bool | None = None
    tip_amount: int | None = None  # cents
    subtotal: int | None = None  # cents
    discount_amount: int | None = None  # cents
    tax_amount: int | None = None  # cents
    total_amount: int | None = None  # cents


class Booking(BookingBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    confirmation_email_sent_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    qr_code_base64: str | None = Field(default=None)
    items: list["BookingItem"] = Relationship(
        back_populates="booking",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    discount_code: Optional["DiscountCode"] = Relationship(back_populates="bookings")

    @property
    def mission_id(self) -> uuid.UUID | None:
        """Get the mission ID from the first booking item's trip."""
        if self.items and len(self.items) > 0:
            return self.items[0].trip.mission_id
        return None

    @property
    def mission(self) -> "Mission | None":
        """Get the mission from the first booking item's trip."""
        if self.items and len(self.items) > 0:
            return self.items[0].trip.mission
        return None


class BookingExperienceDisplay(SQLModel):
    """Trip, mission, launch and boat display data for public booking detail (no auth, works for past trips)."""

    trip_name: str | None = None
    trip_type: str | None = None
    departure_time: str | None = None
    trip_timezone: str | None = None
    check_in_time: str | None = None
    boarding_time: str | None = None
    mission_name: str | None = None
    launch_name: str | None = None
    launch_timestamp: str | None = None
    launch_timezone: str | None = None
    launch_summary: str | None = None
    boat_name: str | None = None
    provider_name: str | None = None
    departure_location: str | None = None
    map_link: str | None = None


class BookingPublic(BookingBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list["BookingItemPublic"]
    qr_code_base64: str | None = None
    mission_id: uuid.UUID | None = None
    mission_name: str | None = None
    trip_name: str | None = None
    trip_type: str | None = None
    discount_code: "DiscountCodePublic | None" = None
    experience_display: "BookingExperienceDisplay | None" = None


# Discount Code Models
class DiscountCodeType(str, enum.Enum):
    percentage = "percentage"
    fixed_amount = "fixed_amount"


class DiscountCodeBase(SQLModel):
    code: str = Field(unique=True, index=True, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    discount_type: DiscountCodeType
    discount_value: float = Field(ge=0)  # percentage 0-1, or cents when fixed_amount
    max_uses: int | None = Field(default=None, ge=1)
    used_count: int = Field(default=0, ge=0)
    is_active: bool = Field(default=True)
    valid_from: datetime | None = Field(default=None)
    valid_until: datetime | None = Field(default=None)
    min_order_amount: int | None = Field(default=None, ge=0)  # cents
    max_discount_amount: int | None = Field(default=None, ge=0)  # cents
    # Access code fields for early_bird booking mode
    is_access_code: bool = Field(default=False)  # Grants early_bird access
    access_code_mission_id: uuid.UUID | None = Field(
        default=None
    )  # Restrict to specific mission


class DiscountCodeCreate(SQLModel):
    code: str = Field(max_length=50)
    description: str | None = Field(default=None, max_length=255)
    discount_type: DiscountCodeType
    discount_value: float = Field(ge=0)  # percentage 0-1, or cents when fixed_amount
    max_uses: int | None = Field(default=None, ge=1)
    is_active: bool = Field(default=True)
    valid_from: datetime | None = Field(default=None)
    valid_until: datetime | None = Field(default=None)
    min_order_amount: int | None = Field(default=None, ge=0)  # cents
    max_discount_amount: int | None = Field(default=None, ge=0)  # cents
    is_access_code: bool = Field(default=False)
    access_code_mission_id: uuid.UUID | None = Field(default=None)


class DiscountCodeUpdate(SQLModel):
    code: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    discount_type: DiscountCodeType | None = None
    discount_value: float | None = Field(default=None, ge=0)
    max_uses: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    valid_from: datetime | None = Field(default=None)
    valid_until: datetime | None = Field(default=None)
    min_order_amount: int | None = Field(default=None, ge=0)  # cents
    max_discount_amount: int | None = Field(default=None, ge=0)  # cents
    is_access_code: bool | None = None
    access_code_mission_id: uuid.UUID | None = Field(default=None)


class DiscountCode(DiscountCodeBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    valid_from: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    valid_until: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
    bookings: list["Booking"] = Relationship(back_populates="discount_code")


class DiscountCodePublic(DiscountCodeBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
