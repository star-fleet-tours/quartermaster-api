"""
CRUD operations for the Quartermaster application.

This module provides database operations organized by domain.
"""

# Import all CRUD functions to maintain backward compatibility
from .boat_pricing import (
    create_boat_pricing,
    delete_boat_pricing,
    get_boat_pricing,
    get_boat_pricing_by_boat,
    update_boat_pricing,
)
from .boats import (
    create_boat,
    delete_boat,
    get_boat,
    get_boats,
    get_boats_by_jurisdiction,
    get_boats_count,
    get_boats_no_relationships,
    update_boat,
)
from .booking_items import (
    create_booking_item,
    delete_booking_item,
    get_booking_item,
    get_booking_items_by_trip,
    get_paid_ticket_count_per_boat_for_trip,
    get_paid_ticket_count_per_boat_per_item_type_for_trip,
    get_ticket_item_count_for_trip_boat,
    get_ticket_item_count_per_type_for_trip_boat,
    reassign_trip_boat_passengers,
    update_booking_item,
)
from .effective_pricing import (
    get_effective_capacity_per_ticket_type,
    get_effective_pricing,
    get_effective_ticket_types_for_trip,
)
from .jurisdictions import (
    create_jurisdiction,
    delete_jurisdiction,
    get_jurisdiction,
    get_jurisdictions,
    get_jurisdictions_by_location,
    get_jurisdictions_count,
    update_jurisdiction,
)
from .launches import (
    create_launch,
    delete_launch,
    get_launch,
    get_launches,
    get_launches_by_location,
    get_launches_count,
    get_launches_no_relationships,
    update_launch,
)
from .locations import (
    create_location,
    delete_location,
    get_location,
    get_locations,
    get_locations_count,
    get_locations_no_relationships,
    update_location,
)
from .merchandise import (
    create_merchandise,
    delete_merchandise,
    get_merchandise,
    get_merchandise_count,
    get_merchandise_list,
    update_merchandise,
)
from .merchandise_variation import (
    create_merchandise_variation,
    delete_merchandise_variation,
    get_merchandise_variation,
    get_merchandise_variation_by_merchandise_and_value,
    list_merchandise_variations_by_merchandise,
    update_merchandise_variation,
)
from .missions import (
    create_mission,
    delete_mission,
    get_active_missions,
    get_mission,
    get_missions,
    get_missions_by_launch,
    get_missions_count,
    get_missions_no_relationships,
    get_missions_with_stats,
    get_public_missions,
    update_mission,
)
from .providers import (
    create_provider,
    delete_provider,
    get_provider,
    get_providers,
    get_providers_by_jurisdiction,
    get_providers_count,
    update_provider,
)
from .trip_boat_pricing import (
    cascade_trip_boat_ticket_type_rename,
    create_trip_boat_pricing,
    delete_trip_boat_pricing,
    get_trip_boat_pricing,
    get_trip_boat_pricing_by_trip_boat,
    update_trip_boat_pricing,
)
from .trip_boats import (
    create_trip_boat,
    delete_trip_boat,
    get_trip_boat,
    get_trip_boats_by_boat,
    get_trip_boats_by_trip,
    get_trip_boats_by_trip_with_boat_provider,
    get_trip_boats_for_trip_ids,
    update_trip_boat,
)
from .trip_merchandise import (
    create_trip_merchandise,
    delete_trip_merchandise,
    get_trip_merchandise,
    get_trip_merchandise_by_trip,
    update_trip_merchandise,
)
from .trips import (
    create_trip,
    delete_trip,
    get_trip,
    get_trip_booking_count_and_codes,
    get_trips,
    get_trips_by_mission,
    get_trips_count,
    get_trips_no_relationships,
    get_trips_with_stats,
    update_trip,
)
from .users import (
    authenticate,
    create_user,
    get_user_by_email,
    update_user,
)

__all__ = [
    # Users
    "authenticate",
    "create_user",
    "get_user_by_email",
    "update_user",
    # Locations
    "create_location",
    "delete_location",
    "get_location",
    "get_locations",
    "get_locations_count",
    "get_locations_no_relationships",
    "update_location",
    # Merchandise
    "create_merchandise",
    "delete_merchandise",
    "get_merchandise",
    "get_merchandise_count",
    "get_merchandise_list",
    "update_merchandise",
    # Merchandise variation
    "create_merchandise_variation",
    "delete_merchandise_variation",
    "get_merchandise_variation",
    "get_merchandise_variation_by_merchandise_and_value",
    "list_merchandise_variations_by_merchandise",
    "update_merchandise_variation",
    # Jurisdictions
    "create_jurisdiction",
    "delete_jurisdiction",
    "get_jurisdiction",
    "get_jurisdictions",
    "get_jurisdictions_by_location",
    "get_jurisdictions_count",
    "update_jurisdiction",
    # Providers
    "create_provider",
    "delete_provider",
    "get_provider",
    "get_providers",
    "get_providers_by_jurisdiction",
    "get_providers_count",
    "update_provider",
    # Launches
    "create_launch",
    "delete_launch",
    "get_launch",
    "get_launches",
    "get_launches_by_location",
    "get_launches_count",
    "get_launches_no_relationships",
    "update_launch",
    # Missions
    "create_mission",
    "delete_mission",
    "get_active_missions",
    "get_mission",
    "get_missions",
    "get_missions_by_launch",
    "get_missions_count",
    "get_missions_no_relationships",
    "get_missions_with_stats",
    "get_public_missions",
    "update_mission",
    # Boats
    "create_boat",
    "delete_boat",
    "get_boat",
    "get_boats",
    "get_boats_by_jurisdiction",
    "get_boats_count",
    "get_boats_no_relationships",
    "update_boat",
    # Trips
    "create_trip",
    "delete_trip",
    "get_trip",
    "get_trip_booking_count_and_codes",
    "get_trips",
    "get_trips_by_mission",
    "get_trips_count",
    "get_trips_no_relationships",
    "get_trips_with_stats",
    "update_trip",
    # Trip Boats
    "create_trip_boat",
    "delete_trip_boat",
    "get_trip_boat",
    "get_trip_boats_by_boat",
    "get_trip_boats_by_trip",
    "get_trip_boats_by_trip_with_boat_provider",
    "get_trip_boats_for_trip_ids",
    "update_trip_boat",
    # Trip Merchandise
    "create_trip_merchandise",
    "delete_trip_merchandise",
    "get_trip_merchandise",
    "get_trip_merchandise_by_trip",
    "update_trip_merchandise",
    # Boat Pricing
    "create_boat_pricing",
    "delete_boat_pricing",
    "get_boat_pricing",
    "get_boat_pricing_by_boat",
    "update_boat_pricing",
    # Trip Boat Pricing
    "cascade_trip_boat_ticket_type_rename",
    "create_trip_boat_pricing",
    "delete_trip_boat_pricing",
    "get_trip_boat_pricing",
    "get_trip_boat_pricing_by_trip_boat",
    "update_trip_boat_pricing",
    # Effective pricing
    "get_effective_capacity_per_ticket_type",
    "get_effective_pricing",
    "get_effective_ticket_types_for_trip",
    # Booking Items
    "create_booking_item",
    "delete_booking_item",
    "get_booking_item",
    "get_booking_items_by_trip",
    "get_paid_ticket_count_per_boat_for_trip",
    "get_paid_ticket_count_per_boat_per_item_type_for_trip",
    "get_ticket_item_count_for_trip_boat",
    "get_ticket_item_count_per_type_for_trip_boat",
    "reassign_trip_boat_passengers",
    "update_booking_item",
]
