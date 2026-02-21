import { NativeSelect } from "@/components/ui/native-select"
import {
  Box,
  Button,
  ButtonGroup,
  Flex,
  HStack,
  IconButton,
  Input,
  Tabs,
  Text,
  VStack,
} from "@chakra-ui/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useRef, useState } from "react"
import {
  FiDollarSign,
  FiEdit,
  FiPlus,
  FiSliders,
  FiTrash2,
  FiUsers,
} from "react-icons/fi"

import {
  type ApiError,
  BoatPricingService,
  BoatsService,
  MerchandiseService,
  TripBoatPricingService,
  TripBoatsService,
  TripMerchandiseService,
  type TripPublic,
  type TripUpdate,
  TripsService,
} from "@/client"
import { MissionDropdown } from "@/components/Common/MissionDropdown"
import {
  DialogActionTrigger,
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Field } from "@/components/ui/field"
import { Switch } from "@/components/ui/switch"
import useCustomToast from "@/hooks/useCustomToast"
import {
  formatCents,
  formatInLocationTimezone,
  formatLocationTimezoneDisplay,
  handleError,
  parseApiDate,
  parseLocationTimeToUtc,
} from "@/utils"
type EditTripTab = "basic-info" | "boats" | "pricing"

interface EditTripProps {
  trip: TripPublic
  /** When set, dialog opens on this tab (e.g. "boats" for Manage Boats). */
  initialTab?: EditTripTab
  /** When set, trigger button shows this label instead of "Edit Trip". */
  triggerLabel?: string
  /** When provided, dialog open state is controlled (e.g. open after duplicate). */
  isOpen?: boolean
  onOpenChange?: (open: boolean) => void
}

const EditTrip = ({
  trip,
  initialTab = "basic-info",
  triggerLabel = "Edit Trip",
  isOpen: controlledOpen,
  onOpenChange: controlledOnOpenChange,
}: EditTripProps) => {
  const [internalOpen, setInternalOpen] = useState(false)
  const isControlled = controlledOpen !== undefined && controlledOnOpenChange != null
  const isOpen = isControlled ? controlledOpen : internalOpen
  const setOpen = isControlled ? controlledOnOpenChange : setInternalOpen
  const [missionId, setMissionId] = useState(trip.mission_id)
  const [name, setName] = useState(trip.name ?? "")
  const [type, setType] = useState(trip.type)
  const [active, setActive] = useState(trip.active ?? true)
  const [unlisted, setUnlisted] = useState(trip.unlisted ?? false)
  const [bookingMode, setBookingMode] = useState(
    trip.booking_mode ?? "private",
  )

  const tz = trip.timezone ?? "UTC"
  const dep = parseApiDate(trip.departure_time)
  const board = parseApiDate(trip.boarding_time)
  const checkIn = parseApiDate(trip.check_in_time)
  const [departureTime, setDepartureTime] = useState(
    formatInLocationTimezone(dep, tz),
  )
  const [salesOpenAt, setSalesOpenAt] = useState(
    (trip as { sales_open_at?: string | null }).sales_open_at
      ? formatInLocationTimezone(
          parseApiDate(
            (trip as { sales_open_at?: string | null }).sales_open_at!,
          ),
          tz,
        )
      : "",
  )
  const [boardingMinutesBeforeDeparture, setBoardingMinutesBeforeDeparture] =
    useState(() =>
      Math.round((dep.getTime() - board.getTime()) / (60 * 1000)),
    )
  const [checkinMinutesBeforeBoarding, setCheckinMinutesBeforeBoarding] =
    useState(() =>
      Math.round((board.getTime() - checkIn.getTime()) / (60 * 1000)),
    )
  const [boatsData, setBoatsData] = useState<any[]>([])
  const [tripBoats, setTripBoats] = useState<any[]>([])
  const [selectedBoatId, setSelectedBoatId] = useState("")
  const [maxCapacity, setMaxCapacity] = useState<number | undefined>(undefined)
  const [isAddingBoat, setIsAddingBoat] = useState(false)
  const [reassignFrom, setReassignFrom] = useState<{
    boat_id: string
    boatName: string
    used: number
  } | null>(null)
  const [reassignToBoatId, setReassignToBoatId] = useState("")
  const [reassignTypeMapping, setReassignTypeMapping] = useState<
    Record<string, string>
  >({})
  const [isReassignSubmitting, setIsReassignSubmitting] = useState(false)
  const [isAddingMerchandise, setIsAddingMerchandise] = useState(false)
  const [merchandiseForm, setMerchandiseForm] = useState({
    merchandise_id: "",
    price_override: "",
    quantity_available_override: "",
  })
  const [selectedTripBoatForPricing, setSelectedTripBoatForPricing] = useState<{
    id: string
    boatId: string
    boatName: string
  } | null>(null)
  const [editingOverrideId, setEditingOverrideId] = useState<string | null>(
    null,
  )
  const [editingOverrideTicketType, setEditingOverrideTicketType] =
    useState("")
  const [editingOverridePrice, setEditingOverridePrice] = useState("")
  const [editingOverrideCapacity, setEditingOverrideCapacity] = useState("")
  const [editingCapacityTripBoatId, setEditingCapacityTripBoatId] = useState<
    string | null
  >(null)
  const [capacityInputValue, setCapacityInputValue] = useState("")
  const [tripBoatPricingForm, setTripBoatPricingForm] = useState({
    ticket_type: "",
    price: "",
    capacity: "",
  })
  const [isAddingTripBoatPricing, setIsAddingTripBoatPricing] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast } = useCustomToast()
  const contentRef = useRef(null)

  const mutation = useMutation({
    mutationFn: (data: TripUpdate) =>
      TripsService.updateTrip({
        tripId: trip.id,
        requestBody: data,
      }),
    onSuccess: () => {
      showSuccessToast("Trip updated successfully.")
      setOpen(false)
    },
    onError: (err: ApiError) => {
      handleError(err)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["trips"] })
    },
  })

  const createMerchandiseMutation = useMutation({
    mutationFn: (body: {
      trip_id: string
      merchandise_id: string
      price_override?: number | null
      quantity_available_override?: number | null
    }) =>
      TripMerchandiseService.createTripMerchandise({
        requestBody: body,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trip-merchandise", trip.id] })
      setIsAddingMerchandise(false)
      setMerchandiseForm({
        merchandise_id: "",
        price_override: "",
        quantity_available_override: "",
      })
    },
    onError: (err: ApiError) => handleError(err),
  })

  const deleteMerchandiseMutation = useMutation({
    mutationFn: (tripMerchandiseId: string) =>
      TripMerchandiseService.deleteTripMerchandise({
        tripMerchandiseId,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trip-merchandise", trip.id] })
    },
    onError: (err: ApiError) => handleError(err),
  })

  const handleAddMerchandise = () => {
    if (!merchandiseForm.merchandise_id) return
    createMerchandiseMutation.mutate({
      trip_id: trip.id,
      merchandise_id: merchandiseForm.merchandise_id,
      price_override: merchandiseForm.price_override
        ? Math.round(Number.parseFloat(merchandiseForm.price_override) * 100)
        : null,
      quantity_available_override: merchandiseForm.quantity_available_override
        ? Number.parseInt(merchandiseForm.quantity_available_override, 10)
        : null,
    })
  }

  const handleRemoveMerchandise = (tripMerchandiseId: string) => {
    deleteMerchandiseMutation.mutate(tripMerchandiseId)
  }

  // Fetch boats
  const { data: allBoats } = useQuery({
    queryKey: ["boats-for-edit-trip"],
    queryFn: () => BoatsService.readBoats({ limit: 100 }),
    enabled: isOpen,
  })

  // Fetch trip boats
  const { data: tripBoatsData, refetch: refetchTripBoats } = useQuery({
    queryKey: ["trip-boats-for-edit", trip.id],
    queryFn: async () => {
      const response = await TripBoatsService.readTripBoatsByTrip({
        tripId: trip.id,
      })
      return response
    },
    enabled: isOpen,
  })

  // Fetch trip merchandise (Merchandise tab)
  const { data: tripMerchandiseList } = useQuery({
    queryKey: ["trip-merchandise", trip.id],
    queryFn: () =>
      TripMerchandiseService.listTripMerchandise({ tripId: trip.id }),
    enabled: isOpen,
  })

  // Catalog for adding merchandise
  const { data: catalogMerchandise } = useQuery({
    queryKey: ["merchandise-catalog"],
    queryFn: () =>
      MerchandiseService.readMerchandiseList({ limit: 500, skip: 0 }),
    enabled: isOpen && isAddingMerchandise,
  })

  // When Add Merchandise form opens and catalog has data, select first item so button is enabled (native select shows first option but state stays "" otherwise)
  useEffect(() => {
    if (
      isAddingMerchandise &&
      catalogMerchandise?.data?.length &&
      !merchandiseForm.merchandise_id
    ) {
      const firstId = catalogMerchandise.data[0].id
      setMerchandiseForm((prev) => ({ ...prev, merchandise_id: firstId }))
    }
  }, [isAddingMerchandise, catalogMerchandise?.data, merchandiseForm.merchandise_id])

  // Boat defaults (BoatPricing) for the boat whose pricing panel is open
  const { data: boatDefaultsList = [] } = useQuery({
    queryKey: ["boat-pricing", selectedTripBoatForPricing?.boatId],
    queryFn: () =>
      BoatPricingService.listBoatPricing({
        boatId: selectedTripBoatForPricing!.boatId,
      }),
    enabled: isOpen && !!selectedTripBoatForPricing?.boatId,
  })

  // Trip boat pricing overrides (when a boat is selected in Boats tab)
  const { data: tripBoatPricingList = [], refetch: refetchTripBoatPricing } =
    useQuery({
      queryKey: ["trip-boat-pricing", selectedTripBoatForPricing?.id],
      queryFn: () =>
        TripBoatPricingService.listTripBoatPricing({
          tripBoatId: selectedTripBoatForPricing!.id,
        }),
      enabled: isOpen && !!selectedTripBoatForPricing?.id,
    })

  const createTripBoatPricingMutation = useMutation({
    mutationFn: (body: {
      ticket_type: string
      price: number
      capacity?: number | null
    }) =>
      TripBoatPricingService.createTripBoatPricing({
        requestBody: {
          trip_boat_id: selectedTripBoatForPricing!.id,
          ticket_type: body.ticket_type,
          price: body.price,
          capacity: body.capacity ?? undefined,
        },
      }),
    onSuccess: () => {
      showSuccessToast("Pricing override added.")
      setTripBoatPricingForm({ ticket_type: "", price: "", capacity: "" })
      setIsAddingTripBoatPricing(false)
      refetchTripBoatPricing()
      queryClient.invalidateQueries({ queryKey: ["trip-boat-pricing"] })
    },
    onError: (err: ApiError) => handleError(err),
  })

  const deleteTripBoatPricingMutation = useMutation({
    mutationFn: (tripBoatPricingId: string) =>
      TripBoatPricingService.deleteTripBoatPricing({ tripBoatPricingId }),
    onSuccess: () => {
      showSuccessToast("Pricing override removed.")
      refetchTripBoatPricing()
      queryClient.invalidateQueries({ queryKey: ["trip-boat-pricing"] })
    },
    onError: (err: ApiError) => handleError(err),
  })

  const updateTripBoatPricingMutation = useMutation({
    mutationFn: (body: {
      tripBoatPricingId: string
      ticket_type?: string
      price: number
      capacity?: number | null
    }) =>
      TripBoatPricingService.updateTripBoatPricing({
        tripBoatPricingId: body.tripBoatPricingId,
        requestBody: {
          ticket_type: body.ticket_type,
          price: body.price,
          ...(body.capacity !== undefined ? { capacity: body.capacity } : {}),
        },
      }),
    onSuccess: () => {
      showSuccessToast("Override updated. Existing bookings updated.")
      setEditingOverrideId(null)
      setEditingOverrideTicketType("")
      setEditingOverridePrice("")
      setEditingOverrideCapacity("")
      refetchTripBoatPricing()
      queryClient.invalidateQueries({ queryKey: ["trip-boat-pricing"] })
      queryClient.invalidateQueries({ queryKey: ["bookings"] })
    },
    onError: (err: ApiError) => handleError(err),
  })

  const handleAddTripBoatPricing = () => {
    const priceDollars = Number.parseFloat(tripBoatPricingForm.price)
    const cap = tripBoatPricingForm.capacity.trim()
      ? Number.parseInt(tripBoatPricingForm.capacity, 10)
      : null
    if (
      !selectedTripBoatForPricing ||
      !tripBoatPricingForm.ticket_type.trim() ||
      Number.isNaN(priceDollars)
    )
      return
    if (cap !== null && (Number.isNaN(cap) || cap < 0)) return
    createTripBoatPricingMutation.mutate({
      ticket_type: tripBoatPricingForm.ticket_type.trim(),
      price: Math.round(priceDollars * 100),
      capacity: cap ?? undefined,
    })
  }

  const updateTripBoatMutation = useMutation({
    mutationFn: (body: {
      tripBoatId: string
      max_capacity?: number | null
      use_only_trip_pricing?: boolean
    }) =>
      TripBoatsService.updateTripBoat({
        tripBoatId: body.tripBoatId,
        requestBody: {
          ...(body.max_capacity !== undefined && {
            max_capacity: body.max_capacity,
          }),
          ...(body.use_only_trip_pricing !== undefined && {
            use_only_trip_pricing: body.use_only_trip_pricing,
          }),
        },
      }),
    onSuccess: async (_, variables) => {
      if (variables.max_capacity !== undefined) {
        showSuccessToast("Capacity updated.")
        setEditingCapacityTripBoatId(null)
        setCapacityInputValue("")
      } else if (variables.use_only_trip_pricing !== undefined) {
        showSuccessToast("Pricing mode updated.")
      }
      await refetchTripBoats()
      queryClient.invalidateQueries({ queryKey: ["trip-boats"] })
      queryClient.invalidateQueries({ queryKey: ["trip-boats-for-edit", trip.id] })
      queryClient.invalidateQueries({ queryKey: ["trips"] })
    },
    onError: (err: ApiError) => handleError(err),
  })

  const selectedTripBoat = selectedTripBoatForPricing
    ? tripBoats.find((tb) => tb.id === selectedTripBoatForPricing.id)
    : null
  const useOnlyTripPricing = selectedTripBoat?.use_only_trip_pricing ?? false

  const handleSaveCapacity = (tripBoatId: string) => {
    const trimmed = capacityInputValue.trim()
    if (trimmed === "") {
      updateTripBoatMutation.mutate({ tripBoatId, max_capacity: null })
      return
    }
    const num = Number.parseInt(trimmed, 10)
    if (Number.isNaN(num) || num < 1) return
    updateTripBoatMutation.mutate({ tripBoatId, max_capacity: num })
  }

  // Update boats data when fetched
  useEffect(() => {
    if (allBoats?.data) {
      setBoatsData(allBoats.data)
    }
  }, [allBoats])

  // Update trip boats when fetched
  useEffect(() => {
    if (tripBoatsData) {
      setTripBoats(Array.isArray(tripBoatsData) ? (tripBoatsData as any[]) : [])
    }
  }, [tripBoatsData])

  // Clear override edit state when switching to another boat
  useEffect(() => {
    setEditingOverrideId(null)
    setEditingOverridePrice("")
  }, [selectedTripBoatForPricing?.id])

  // Default type mapping when target boat is selected for reassign
  useEffect(() => {
    if (!reassignFrom || !reassignToBoatId) {
      return
    }
    const fromBoat = tripBoats.find((tb) => tb.boat_id === reassignFrom.boat_id)
    const toBoat = tripBoats.find((tb) => tb.boat_id === reassignToBoatId)
    const used: Record<string, number> =
      fromBoat && "used_per_ticket_type" in fromBoat
        ? (fromBoat as { used_per_ticket_type?: Record<string, number> })
            .used_per_ticket_type ?? {}
        : {}
    const targetTypes: string[] =
      toBoat && "pricing" in toBoat && Array.isArray((toBoat as { pricing?: { ticket_type: string }[] }).pricing)
        ? ((toBoat as { pricing: { ticket_type: string }[] }).pricing ?? []).map(
            (p) => p.ticket_type,
          )
        : []
    const sourceTypesWithQty = Object.entries(used).filter(([, qty]) => qty > 0)
    if (sourceTypesWithQty.length === 0 || targetTypes.length === 0) {
      setReassignTypeMapping({})
      return
    }
    const next: Record<string, string> = {}
    for (const [srcType] of sourceTypesWithQty) {
      next[srcType] = targetTypes.includes(srcType)
        ? srcType
        : targetTypes[0] ?? ""
    }
    setReassignTypeMapping(next)
  }, [reassignFrom, reassignToBoatId, tripBoats])

  const reassignCanSubmit = useMemo(() => {
    if (!reassignFrom || !reassignToBoatId) return false
    const fromBoat = tripBoats.find((tb) => tb.boat_id === reassignFrom.boat_id)
    const used: Record<string, number> =
      fromBoat && "used_per_ticket_type" in fromBoat
        ? (fromBoat as { used_per_ticket_type?: Record<string, number> })
            .used_per_ticket_type ?? {}
        : {}
    const sourceTypesWithQty = Object.entries(used).filter(([, qty]) => qty > 0)
    if (sourceTypesWithQty.length === 0) return true
    return sourceTypesWithQty.every(
      ([t]) => reassignTypeMapping[t]?.trim() !== "",
    )
  }, [reassignFrom, reassignToBoatId, reassignTypeMapping, tripBoats])

  // Sync inputs when dialog opens or trip changes (e.g. after duplicate)
  useEffect(() => {
    if (isOpen) {
      const zone = trip.timezone ?? "UTC"
      setMissionId(trip.mission_id)
      setName(trip.name ?? "")
      setType(trip.type)
      setActive(trip.active ?? true)
      setUnlisted(trip.unlisted ?? false)
      setBookingMode(trip.booking_mode ?? "private")
      setDepartureTime(
        formatInLocationTimezone(parseApiDate(trip.departure_time), zone),
      )
      const salesOpen = (trip as { sales_open_at?: string | null }).sales_open_at
      setSalesOpenAt(
        salesOpen
          ? formatInLocationTimezone(parseApiDate(salesOpen), zone)
          : "",
      )
      const d = parseApiDate(trip.departure_time)
      const b = parseApiDate(trip.boarding_time)
      const c = parseApiDate(trip.check_in_time)
      setBoardingMinutesBeforeDeparture(
        Math.round((d.getTime() - b.getTime()) / (60 * 1000)),
      )
      setCheckinMinutesBeforeBoarding(
        Math.round((b.getTime() - c.getTime()) / (60 * 1000)),
      )
    }
  }, [
    isOpen,
    trip.id,
    trip.mission_id,
    trip.name,
    trip.type,
    trip.active,
    trip.unlisted,
    trip.booking_mode,
    trip.check_in_time,
    trip.boarding_time,
    trip.departure_time,
    trip.timezone,
    (trip as { sales_open_at?: string | null }).sales_open_at,
  ])

  // Create a map of boat ids to boat objects for quick lookup
  const boatsMap = new Map<string, any>()
  if (boatsData) {
    boatsData.forEach((boat) => {
      boatsMap.set(boat.id, boat)
    })
  }

  // Handle adding a boat
  const handleAddBoat = async () => {
    if (!selectedBoatId) return

    try {
      // Check if this boat is already associated with this trip
      const exists = tripBoats.some((tb) => tb.boat_id === selectedBoatId)
      if (exists) {
        showSuccessToast("This boat is already associated with this trip")
        return
      }

      await TripBoatsService.createTripBoat({
        requestBody: {
          trip_id: trip.id,
          boat_id: selectedBoatId,
          max_capacity: maxCapacity || null,
          use_only_trip_pricing: false,
        },
      })

      showSuccessToast("The boat has been successfully added to this trip")

      // Reset form and refresh data
      setSelectedBoatId("")
      setMaxCapacity(undefined)
      setIsAddingBoat(false)
      await refetchTripBoats()
      queryClient.invalidateQueries({ queryKey: ["trip-boats"] })
      queryClient.invalidateQueries({ queryKey: ["trip-boats-for-edit", trip.id] })
    } catch (error) {
      console.error("Error adding boat to trip:", error)
      handleError(error as ApiError)
    }
  }

  // Handle removing a boat
  const handleRemoveBoat = async (tripBoatId: string) => {
    try {
      await TripBoatsService.deleteTripBoat({
        tripBoatId,
      })

      showSuccessToast("The boat has been removed from this trip")

      // Refresh data
      await refetchTripBoats()
      queryClient.invalidateQueries({ queryKey: ["trip-boats"] })
      queryClient.invalidateQueries({ queryKey: ["trip-boats-for-edit", trip.id] })
    } catch (error) {
      console.error("Error removing boat from trip:", error)
      handleError(error as ApiError)
    }
  }

  // Reassign passengers from one boat to another
  const handleReassignConfirm = async () => {
    if (!reassignFrom || !reassignToBoatId) return
    setIsReassignSubmitting(true)
    try {
      const res = await TripsService.reassignTripBoat({
        tripId: trip.id,
        requestBody: {
          from_boat_id: reassignFrom.boat_id,
          to_boat_id: reassignToBoatId,
          type_mapping: reassignTypeMapping,
        },
      })
      showSuccessToast(`Moved ${res.moved} passenger(s) to the selected boat.`)
      // Await refetch to ensure fresh data before closing dialog
      await refetchTripBoats()
      setReassignFrom(null)
      setReassignToBoatId("")
      setReassignTypeMapping({})
      // Invalidate queries for other components using trip boats data
      queryClient.invalidateQueries({ queryKey: ["trip-boats"] })
      queryClient.invalidateQueries({ queryKey: ["trip-boats-for-edit", trip.id] })
      queryClient.invalidateQueries({ queryKey: ["trips"] })
    } catch (error) {
      console.error("Error reassigning passengers:", error)
      handleError(error as ApiError)
    } finally {
      setIsReassignSubmitting(false)
    }
  }

  const handleSubmit = () => {
    if (!missionId || !departureTime) return
    if (
      boardingMinutesBeforeDeparture < 0 ||
      checkinMinutesBeforeBoarding < 0
    )
      return

    mutation.mutate({
      mission_id: missionId,
      name: name || null,
      type: type,
      active: active,
      unlisted: unlisted,
      booking_mode: bookingMode,
      sales_open_at: salesOpenAt
        ? parseLocationTimeToUtc(salesOpenAt, tz)
        : null,
      departure_time: parseLocationTimeToUtc(departureTime, tz),
      boarding_minutes_before_departure: boardingMinutesBeforeDeparture,
      checkin_minutes_before_boarding: checkinMinutesBeforeBoarding,
    })
  }

  return (
    <>
      <DialogRoot
        size={{ base: "xs", md: "md" }}
        placement="center"
        open={isOpen}
        onOpenChange={({ open }) => setOpen(open)}
      >
        {!isControlled && (
          <DialogTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              color="dark.accent.primary"
            >
              <FiEdit fontSize="16px" />
              {triggerLabel}
            </Button>
          </DialogTrigger>
        )}

        <DialogContent ref={contentRef}>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleSubmit()
            }}
          >
            <DialogCloseTrigger />
            <DialogHeader>
              <DialogTitle>Edit Trip</DialogTitle>
            </DialogHeader>
            <DialogBody>
              <Tabs.Root defaultValue={initialTab} variant="subtle">
                <Tabs.List>
                  <Tabs.Trigger value="basic-info">Basic Info</Tabs.Trigger>
                  <Tabs.Trigger value="boats">Boats</Tabs.Trigger>
                  <Tabs.Trigger value="pricing">Merchandise</Tabs.Trigger>
                </Tabs.List>

                <Tabs.Content value="basic-info">
                  <VStack gap={4}>
                    <Field label="Mission" required>
                      <MissionDropdown
                        id="mission_id"
                        value={missionId}
                        onChange={setMissionId}
                        isDisabled={mutation.isPending}
                        portalRef={contentRef}
                      />
                    </Field>

                    <Field
                      label="Name"
                      helperText="Optional custom label for this trip"
                    >
                      <Input
                        id="name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Trip name (optional)"
                        disabled={mutation.isPending}
                      />
                    </Field>

                    <Field label="Type" required>
                      <NativeSelect
                        id="type"
                        value={type}
                        onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                          setType(e.target.value)
                        }
                        disabled={mutation.isPending}
                      >
                        <option value="launch_viewing">Launch Viewing</option>
                        <option value="pre_launch">Pre-Launch</option>
                      </NativeSelect>
                    </Field>

                    <Field
                      label="Booking Mode"
                      helperText="Controls who can book this trip"
                    >
                      <NativeSelect
                        id="booking_mode"
                        value={bookingMode}
                        onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                          setBookingMode(e.target.value)
                        }
                        disabled={mutation.isPending}
                      >
                        <option value="private">Private (Admin Only)</option>
                        <option value="early_bird">
                          Early Bird (Access Code Required)
                        </option>
                        <option value="public">Public (Open to All)</option>
                      </NativeSelect>
                    </Field>

                    <Field
                      label={`Sales Open (${formatLocationTimezoneDisplay(
                        tz,
                      )})`}
                      helperText="Trip is not bookable until this time. Leave empty for no restriction."
                    >
                      <Input
                        id="sales_open_at"
                        type="datetime-local"
                        value={salesOpenAt}
                        onChange={(e) => setSalesOpenAt(e.target.value)}
                        placeholder={`Enter time in ${tz}`}
                        disabled={mutation.isPending}
                      />
                    </Field>

                    <Field
                      label={`Departure Time (${formatLocationTimezoneDisplay(
                        tz,
                      )})`}
                      required
                    >
                      <Input
                        id="departure_time"
                        type="datetime-local"
                        value={departureTime}
                        onChange={(e) => setDepartureTime(e.target.value)}
                        placeholder={`Enter time in ${tz}`}
                        disabled={mutation.isPending}
                      />
                    </Field>

                    <Field
                      label="Boarding (minutes before departure)"
                      helperText="When boarding starts relative to departure"
                    >
                      <Input
                        id="boarding_minutes"
                        type="number"
                        min={0}
                        value={boardingMinutesBeforeDeparture}
                        onChange={(e) =>
                          setBoardingMinutesBeforeDeparture(
                            Math.max(
                              0,
                              parseInt(e.target.value, 10) || 0,
                            ),
                          )
                        }
                        disabled={mutation.isPending}
                      />
                    </Field>

                    <Field
                      label="Check-in (minutes before boarding)"
                      helperText="When check-in opens relative to boarding"
                    >
                      <Input
                        id="checkin_minutes"
                        type="number"
                        min={0}
                        value={checkinMinutesBeforeBoarding}
                        onChange={(e) =>
                          setCheckinMinutesBeforeBoarding(
                            Math.max(
                              0,
                              parseInt(e.target.value, 10) || 0,
                            ),
                          )
                        }
                        disabled={mutation.isPending}
                      />
                    </Field>

                    <Field>
                      <Flex
                        alignItems="center"
                        justifyContent="space-between"
                        width="100%"
                      >
                        <Text>Active</Text>
                        <Box>
                          <Switch
                            checked={active}
                            onCheckedChange={({ checked }) => setActive(checked === true)}
                            disabled={mutation.isPending}
                            inputProps={{ id: "active" }}
                          />
                        </Box>
                      </Flex>
                    </Field>
                    <Field
                      helperText="Only visible via direct link; excluded from public listing."
                    >
                      <Flex
                        alignItems="center"
                        justifyContent="space-between"
                        width="100%"
                      >
                        <Text>Unlisted</Text>
                        <Box>
                          <Switch
                            checked={unlisted}
                            onCheckedChange={({ checked }) => setUnlisted(checked === true)}
                            disabled={mutation.isPending}
                            inputProps={{ id: "unlisted" }}
                          />
                        </Box>
                      </Flex>
                    </Field>
                  </VStack>
                </Tabs.Content>

                {/* Boats Tab */}
                <Tabs.Content value="boats">
                  <Box width="100%">
                    <Text fontWeight="bold" mb={2}>
                      Associated Boats
                    </Text>

                    {/* List of current boats */}
                    {tripBoats && tripBoats.length > 0 ? (
                      <VStack align="stretch" mb={4} gap={2}>
                        {tripBoats.map((tripBoat) => {
                          const boat = boatsMap.get(tripBoat.boat_id)
                          const maxCap =
                            tripBoat.max_capacity ?? boat?.capacity ?? 0
                          const remaining =
                            "remaining_capacity" in tripBoat
                              ? (tripBoat as { remaining_capacity: number })
                                  .remaining_capacity
                              : maxCap
                          const used = maxCap - remaining
                          const hasBookings = remaining < maxCap
                          const isPricingOpen =
                            selectedTripBoatForPricing?.id === tripBoat.id
                          const pricing =
                            "pricing" in tripBoat &&
                            Array.isArray(
                              (tripBoat as { pricing?: unknown[] }).pricing,
                            )
                              ? (
                                  tripBoat as {
                                    pricing: Array<{
                                      ticket_type: string
                                      price: number
                                      capacity: number
                                      remaining: number
                                    }>
                                  }
                                ).pricing
                              : []
                          return (
                            <Box key={tripBoat.id}>
                              <Flex
                                justify="space-between"
                                align="center"
                                p={2}
                                borderWidth="1px"
                                borderRadius="md"
                              >
                                <Box>
                                  <Text color="gray.100" fontWeight="medium">
                                    {boat?.name || "Unknown"}
                                  </Text>
                                  <Text
                                    fontSize="xs"
                                    color="gray.300"
                                    mt={0.5}
                                    lineHeight="1.2"
                                  >
                                    {used} of {maxCap} seats taken ({remaining}{" "}
                                    remaining)
                                  </Text>
                                  {pricing.length > 0 && (
                                    <VStack align="start" gap={0}>
                                      {pricing.map((p) => (
                                        <Text
                                          key={p.ticket_type}
                                          fontSize="xs"
                                          color="gray.500"
                                          lineHeight="1.2"
                                        >
                                          {p.ticket_type}: $
                                          {formatCents(p.price)} ({p.remaining}/
                                          {p.capacity} left)
                                        </Text>
                                      ))}
                                    </VStack>
                                  )}
                                </Box>
                                <Flex gap={1} align="center">
                                  {hasBookings && (
                                    <IconButton
                                      aria-label="Reassign passengers"
                                      title="Reassign"
                                      size="sm"
                                      variant="ghost"
                                      onClick={() =>
                                        setReassignFrom({
                                          boat_id: tripBoat.boat_id,
                                          boatName: boat?.name || "Unknown",
                                          used,
                                        })
                                      }
                                    >
                                      <FiUsers />
                                    </IconButton>
                                  )}
                                  <IconButton
                                    aria-label="Pricing overrides"
                                    title="Pricing"
                                    size="sm"
                                    variant="ghost"
                                    onClick={() =>
                                      setSelectedTripBoatForPricing(
                                        isPricingOpen
                                          ? null
                                          : {
                                              id: tripBoat.id,
                                              boatId: tripBoat.boat_id,
                                              boatName: boat?.name || "Unknown",
                                            },
                                      )
                                    }
                                  >
                                    <FiDollarSign />
                                  </IconButton>
                                  <IconButton
                                    aria-label="Capacity override"
                                    title="Capacity"
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => {
                                      const isCapacityOpen =
                                        editingCapacityTripBoatId ===
                                        tripBoat.id
                                      if (isCapacityOpen) {
                                        setEditingCapacityTripBoatId(null)
                                        setCapacityInputValue("")
                                      } else {
                                        setEditingCapacityTripBoatId(
                                          tripBoat.id,
                                        )
                                        setCapacityInputValue(
                                          tripBoat.max_capacity != null
                                            ? String(tripBoat.max_capacity)
                                            : boat?.capacity != null
                                              ? String(boat.capacity)
                                              : "",
                                        )
                                      }
                                    }}
                                  >
                                    <FiSliders />
                                  </IconButton>
                                  <IconButton
                                    aria-label="Remove boat"
                                    children={<FiTrash2 />}
                                    size="sm"
                                    variant="ghost"
                                    colorScheme="red"
                                    disabled={hasBookings}
                                    title={
                                      hasBookings
                                        ? "Cannot remove: boat has booked passengers."
                                        : undefined
                                    }
                                    onClick={() => {
                                      if (
                                        tripBoat.id ===
                                        selectedTripBoatForPricing?.id
                                      ) {
                                        setSelectedTripBoatForPricing(null)
                                      }
                                      if (
                                        tripBoat.id ===
                                        editingCapacityTripBoatId
                                      ) {
                                        setEditingCapacityTripBoatId(null)
                                      }
                                      handleRemoveBoat(tripBoat.id)
                                    }}
                                  />
                                </Flex>
                              </Flex>
                              {editingCapacityTripBoatId === tripBoat.id && (
                                <Box
                                  mt={2}
                                  ml={2}
                                  p={3}
                                  borderWidth="1px"
                                  borderRadius="md"
                                  borderColor="gray.400"
                                  _dark={{ borderColor: "gray.600" }}
                                >
                                  <Text fontWeight="bold" mb={2} fontSize="sm">
                                    Capacity override for{" "}
                                    {boat?.name || "Unknown"}
                                  </Text>
                                  <Text fontSize="sm" color="gray.500" mb={2}>
                                    Boat default: {boat?.capacity ?? "—"} seats.
                                    Set a lower limit for this trip or leave
                                    default.
                                  </Text>
                                  <HStack
                                    gap={2}
                                    align="center"
                                    flexWrap="wrap"
                                  >
                                    <Input
                                      type="number"
                                      min={used}
                                      size="sm"
                                      width="24"
                                      placeholder={String(boat?.capacity ?? "")}
                                      value={capacityInputValue}
                                      onChange={(e) =>
                                        setCapacityInputValue(e.target.value)
                                      }
                                    />
                                    <Button
                                      size="xs"
                                      variant="ghost"
                                      onClick={() => {
                                        updateTripBoatMutation.mutate({
                                          tripBoatId: tripBoat.id,
                                          max_capacity: null,
                                        })
                                      }}
                                      loading={updateTripBoatMutation.isPending}
                                    >
                                      Use default
                                    </Button>
                                    <Button
                                      size="xs"
                                      onClick={() =>
                                        handleSaveCapacity(tripBoat.id)
                                      }
                                      loading={updateTripBoatMutation.isPending}
                                      disabled={
                                        capacityInputValue.trim() === "" ||
                                        (() => {
                                          const n = Number.parseInt(
                                            capacityInputValue.trim(),
                                            10,
                                          )
                                          return (
                                            Number.isNaN(n) || n < 1 || n < used
                                          )
                                        })()
                                      }
                                    >
                                      Save
                                    </Button>
                                    <Button
                                      size="xs"
                                      variant="ghost"
                                      onClick={() => {
                                        setEditingCapacityTripBoatId(null)
                                        setCapacityInputValue("")
                                      }}
                                    >
                                      Cancel
                                    </Button>
                                  </HStack>
                                </Box>
                              )}
                              {isPricingOpen && (
                                <Box
                                  mt={2}
                                  ml={2}
                                  p={3}
                                  borderWidth="1px"
                                  borderRadius="md"
                                  borderColor="gray.400"
                                  _dark={{ borderColor: "gray.600" }}
                                >
                                  <HStack justify="space-between" mb={2}>
                                    <Text fontWeight="bold">
                                      Pricing overrides for{" "}
                                      {boat?.name || "Unknown"}
                                    </Text>
                                    <Button
                                      size="xs"
                                      variant="ghost"
                                      onClick={() => {
                                        setSelectedTripBoatForPricing(null)
                                        setIsAddingTripBoatPricing(false)
                                        setEditingOverrideId(null)
                                        setEditingOverridePrice("")
                                        setEditingOverrideCapacity("")
                                      }}
                                    >
                                      Close
                                    </Button>
                                  </HStack>
                                  <HStack
                                    justify="space-between"
                                    align="center"
                                    mb={2}
                                    p={2}
                                    borderWidth="1px"
                                    borderRadius="md"
                                    borderColor="gray.300"
                                    _dark={{ borderColor: "gray.600" }}
                                  >
                                    <Box>
                                      <Text fontSize="sm" fontWeight="medium">
                                        Use only trip-specific pricing
                                      </Text>
                                      <Text fontSize="xs" color="gray.500">
                                        {useOnlyTripPricing
                                          ? "Boat defaults ignored. Define all ticket types below."
                                          : "Boat defaults apply; overrides replace price/capacity."}
                                      </Text>
                                    </Box>
                                    <Switch
                                      checked={useOnlyTripPricing}
                                      onCheckedChange={({ checked }) => {
                                        if (selectedTripBoatForPricing) {
                                          updateTripBoatMutation.mutate({
                                            tripBoatId:
                                              selectedTripBoatForPricing.id,
                                            use_only_trip_pricing: checked,
                                          })
                                        }
                                      }}
                                      disabled={
                                        updateTripBoatMutation.isPending
                                      }
                                    />
                                  </HStack>
                                  <Text fontSize="xs" color="gray.400" mb={2}>
                                    {useOnlyTripPricing
                                      ? "Define all ticket types for this trip. Boat defaults are ignored."
                                      : "Boat defaults apply unless you add an override for this trip. Overrides replace the default price for that ticket type."}
                                  </Text>
                                  {!useOnlyTripPricing && (
                                    <Box mb={3}>
                                      <Text
                                        fontSize="sm"
                                        fontWeight="bold"
                                        mb={2}
                                        color="gray.500"
                                      >
                                        Boat defaults (Edit Boat to change)
                                      </Text>
                                      {boatDefaultsList.length > 0 ? (
                                        <VStack align="stretch" gap={1}>
                                          {boatDefaultsList.map((bp) => (
                                            <HStack
                                              key={bp.id}
                                              justify="space-between"
                                              p={2}
                                              borderWidth="1px"
                                              borderRadius="md"
                                              borderColor="gray.400"
                                              _dark={{
                                                borderColor: "gray.600",
                                                bg: "gray.800",
                                              }}
                                            >
                                              <Text fontSize="sm">
                                                {bp.ticket_type}
                                              </Text>
                                              <Text
                                                fontSize="sm"
                                                color="gray.500"
                                              >
                                                ${formatCents(bp.price)}{" "}
                                                (default)
                                              </Text>
                                            </HStack>
                                          ))}
                                        </VStack>
                                      ) : (
                                        <Text fontSize="sm" color="gray.500">
                                          No defaults. Add ticket types in Edit
                                          Boat.
                                        </Text>
                                      )}
                                    </Box>
                                  )}
                                  <Text
                                    fontSize="sm"
                                    fontWeight="bold"
                                    mb={2}
                                    color="gray.700"
                                    _dark={{ color: "gray.300" }}
                                  >
                                    {useOnlyTripPricing
                                      ? "Ticket types for this trip"
                                      : "Overrides for this trip"}
                                  </Text>
                                  <VStack align="stretch" gap={2}>
                                    {tripBoatPricingList.map((p) => {
                                      const isEditing =
                                        editingOverrideId === p.id
                                      return (
                                        <Box
                                          key={p.id}
                                          p={2}
                                          borderWidth="1px"
                                          borderRadius="md"
                                          borderColor="gray.600"
                                        >
                                          {isEditing ? (
                                            <VStack
                                              align="stretch"
                                              gap={2}
                                              width="100%"
                                              minWidth={0}
                                            >
                                              <HStack
                                                gap={2}
                                                flexWrap="wrap"
                                                align="flex-end"
                                              >
                                                <Field label="Ticket type" flex="1 1 120px" minWidth="100px">
                                                  <Input
                                                    size="sm"
                                                    value={
                                                      editingOverrideTicketType
                                                    }
                                                    onChange={(e) =>
                                                      setEditingOverrideTicketType(
                                                        e.target.value,
                                                      )
                                                    }
                                                    placeholder="e.g. VIP, Premium"
                                                  />
                                                </Field>
                                                <Field label="Price ($)" flex="1 1 80px" minWidth="70px">
                                                  <Input
                                                    type="number"
                                                    step="0.01"
                                                    min="0"
                                                    size="sm"
                                                    value={editingOverridePrice}
                                                    onChange={(e) =>
                                                      setEditingOverridePrice(
                                                        e.target.value,
                                                      )
                                                    }
                                                    placeholder="0.00"
                                                  />
                                                </Field>
                                                <Field label="Capacity (opt)" flex="1 1 70px" minWidth="60px">
                                                  <Input
                                                    type="number"
                                                    min="0"
                                                    size="sm"
                                                    value={
                                                      editingOverrideCapacity
                                                    }
                                                    onChange={(e) =>
                                                      setEditingOverrideCapacity(
                                                        e.target.value,
                                                      )
                                                    }
                                                    placeholder="—"
                                                    title="Capacity override (optional)"
                                                  />
                                                </Field>
                                              </HStack>
                                              <HStack justify="flex-end" gap={2}>
                                                <Button
                                                  size="xs"
                                                  variant="ghost"
                                                  onClick={() => {
                                                    setEditingOverrideId(null)
                                                    setEditingOverrideTicketType(
                                                      "",
                                                    )
                                                    setEditingOverridePrice("")
                                                    setEditingOverrideCapacity(
                                                      "",
                                                    )
                                                  }}
                                                >
                                                  Cancel
                                                </Button>
                                                <Button
                                                  size="xs"
                                                  onClick={() => {
                                                    const ticketType =
                                                      editingOverrideTicketType.trim()
                                                    const cents = Math.round(
                                                      Number.parseFloat(
                                                        editingOverridePrice,
                                                      ) * 100,
                                                    )
                                                    if (
                                                      ticketType &&
                                                      !Number.isNaN(cents) &&
                                                      cents >= 0
                                                    ) {
                                                      const cap =
                                                        editingOverrideCapacity.trim()
                                                          ? Number.parseInt(
                                                              editingOverrideCapacity,
                                                              10,
                                                            )
                                                          : null
                                                      if (
                                                        cap !== null &&
                                                        (Number.isNaN(cap) ||
                                                          cap < 0)
                                                      )
                                                        return
                                                      updateTripBoatPricingMutation.mutate(
                                                        {
                                                          tripBoatPricingId:
                                                            p.id,
                                                          ticket_type:
                                                            ticketType,
                                                          price: cents,
                                                          capacity:
                                                            cap ?? undefined,
                                                        },
                                                      )
                                                    }
                                                  }}
                                                  loading={
                                                    updateTripBoatPricingMutation.isPending
                                                  }
                                                  disabled={
                                                    !editingOverrideTicketType.trim() ||
                                                    !editingOverridePrice ||
                                                    Number.isNaN(
                                                      Number.parseFloat(
                                                        editingOverridePrice,
                                                      ),
                                                    )
                                                  }
                                                >
                                                  Save
                                                </Button>
                                              </HStack>
                                            </VStack>
                                          ) : (
                                            <HStack
                                              justify="space-between"
                                              align="center"
                                              flex={1}
                                              gap={2}
                                            >
                                              <HStack gap={2} flex={1} minWidth={0}>
                                                <Text fontWeight="medium">
                                                  {p.ticket_type}
                                                </Text>
                                                <Text
                                                  fontSize="sm"
                                                  color="gray.500"
                                                >
                                                  ${formatCents(p.price)}
                                                  {!useOnlyTripPricing &&
                                                    " (override)"}
                                                  {p.capacity != null
                                                    ? `, ${p.capacity} seats`
                                                    : ""}
                                                </Text>
                                              </HStack>
                                          {!isEditing && (
                                            <HStack gap={1}>
                                              <Button
                                                size="xs"
                                                variant="ghost"
                                                onClick={() => {
                                                  setEditingOverrideId(p.id)
                                                  setEditingOverrideTicketType(
                                                    p.ticket_type,
                                                  )
                                                  setEditingOverridePrice(
                                                    (p.price / 100).toFixed(2),
                                                  )
                                                  setEditingOverrideCapacity(
                                                    p.capacity != null
                                                      ? String(p.capacity)
                                                      : "",
                                                  )
                                                }}
                                              >
                                                <FiEdit fontSize="12px" />
                                                Edit
                                              </Button>
                                              <IconButton
                                                aria-label="Remove override"
                                                size="sm"
                                                variant="ghost"
                                                colorScheme="red"
                                                onClick={() =>
                                                  deleteTripBoatPricingMutation.mutate(
                                                    p.id,
                                                  )
                                                }
                                                disabled={
                                                  deleteTripBoatPricingMutation.isPending
                                                }
                                              >
                                                <FiTrash2 />
                                              </IconButton>
                                            </HStack>
                                          )}
                                        </HStack>
                                          )}
                                        </Box>
                                      )
                                    })}
                                    {tripBoatPricingList.length === 0 &&
                                      !isAddingTripBoatPricing && (
                                        <Text
                                          fontSize="sm"
                                          color="gray.500"
                                          py={2}
                                        >
                                          {useOnlyTripPricing
                                            ? "No ticket types defined. Add at least one to offer tickets."
                                            : "No overrides. Boat default pricing applies."}
                                        </Text>
                                      )}
                                  </VStack>
                                  {isAddingTripBoatPricing ? (
                                    <VStack
                                      align="stretch"
                                      gap={2}
                                      mt={3}
                                      p={2}
                                      borderWidth="1px"
                                      borderRadius="md"
                                    >
                                      <HStack width="100%" align="flex-end">
                                        <Box flex={1}>
                                          <Text fontSize="sm" mb={1}>
                                            Ticket type
                                          </Text>
                                          <NativeSelect
                                            value={(() => {
                                              const defaultsNotOverridden =
                                                boatDefaultsList.filter(
                                                  (bp) =>
                                                    !tripBoatPricingList.some(
                                                      (p) =>
                                                        p.ticket_type ===
                                                        bp.ticket_type,
                                                    ),
                                                )
                                              const isDefault =
                                                defaultsNotOverridden.some(
                                                  (bp) =>
                                                    bp.ticket_type ===
                                                    tripBoatPricingForm.ticket_type,
                                                )
                                              if (isDefault)
                                                return tripBoatPricingForm.ticket_type
                                              if (
                                                tripBoatPricingForm.ticket_type
                                              )
                                                return "__other__"
                                              return ""
                                            })()}
                                            onChange={(
                                              e: React.ChangeEvent<HTMLSelectElement>,
                                            ) => {
                                              const v = e.target.value
                                              setTripBoatPricingForm(
                                                (prev) => ({
                                                  ...prev,
                                                  ticket_type:
                                                    v === "__other__" ? "" : v,
                                                }),
                                              )
                                            }}
                                          >
                                            <option value="">
                                              Select type
                                            </option>
                                            {boatDefaultsList
                                              .filter(
                                                (bp) =>
                                                  !tripBoatPricingList.some(
                                                    (p) =>
                                                      p.ticket_type ===
                                                      bp.ticket_type,
                                                  ),
                                              )
                                              .map((bp) => (
                                                <option
                                                  key={bp.id}
                                                  value={bp.ticket_type}
                                                >
                                                  {bp.ticket_type} (default $
                                                  {formatCents(bp.price)})
                                                </option>
                                              ))}
                                            <option value="__other__">
                                              Other (type below)
                                            </option>
                                          </NativeSelect>
                                          {(() => {
                                            const defaultsNotOverridden =
                                              boatDefaultsList.filter(
                                                (bp) =>
                                                  !tripBoatPricingList.some(
                                                    (p) =>
                                                      p.ticket_type ===
                                                      bp.ticket_type,
                                                  ),
                                              )
                                            const isDefault =
                                              tripBoatPricingForm.ticket_type &&
                                              defaultsNotOverridden.some(
                                                (bp) =>
                                                  bp.ticket_type ===
                                                  tripBoatPricingForm.ticket_type,
                                              )
                                            return !isDefault ? (
                                              <Input
                                                mt={2}
                                                size="sm"
                                                value={
                                                  tripBoatPricingForm.ticket_type
                                                }
                                                onChange={(e) =>
                                                  setTripBoatPricingForm(
                                                    (prev) => ({
                                                      ...prev,
                                                      ticket_type:
                                                        e.target.value,
                                                    }),
                                                  )
                                                }
                                                placeholder="e.g. VIP, Premium"
                                              />
                                            ) : null
                                          })()}
                                        </Box>
                                        <Box flex={1}>
                                          <Text fontSize="sm" mb={1}>
                                            Price ($)
                                          </Text>
                                          <Input
                                            type="number"
                                            step="0.01"
                                            min="0"
                                            value={tripBoatPricingForm.price}
                                            onChange={(e) =>
                                              setTripBoatPricingForm({
                                                ...tripBoatPricingForm,
                                                price: e.target.value,
                                              })
                                            }
                                            placeholder="0.00"
                                          />
                                        </Box>
                                        <Box flex={1}>
                                          <Text fontSize="sm" mb={1}>
                                            Capacity (optional)
                                          </Text>
                                          <Input
                                            type="number"
                                            min="0"
                                            value={tripBoatPricingForm.capacity}
                                            onChange={(e) =>
                                              setTripBoatPricingForm({
                                                ...tripBoatPricingForm,
                                                capacity: e.target.value,
                                              })
                                            }
                                            placeholder="Override seats"
                                          />
                                        </Box>
                                      </HStack>
                                      <HStack width="100%" justify="flex-end">
                                        <Button
                                          size="sm"
                                          variant="ghost"
                                          onClick={() =>
                                            setIsAddingTripBoatPricing(false)
                                          }
                                        >
                                          Cancel
                                        </Button>
                                        <Button
                                          size="sm"
                                          onClick={handleAddTripBoatPricing}
                                          loading={
                                            createTripBoatPricingMutation.isPending
                                          }
                                          disabled={
                                            !tripBoatPricingForm.ticket_type.trim() ||
                                            !tripBoatPricingForm.price ||
                                            Number.isNaN(
                                              Number.parseFloat(
                                                tripBoatPricingForm.price,
                                              ),
                                            )
                                          }
                                        >
                                          {useOnlyTripPricing
                                            ? "Add"
                                            : "Add override"}
                                        </Button>
                                      </HStack>
                                    </VStack>
                                  ) : (
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      mt={2}
                                      onClick={() =>
                                        setIsAddingTripBoatPricing(true)
                                      }
                                    >
                                      <FiPlus style={{ marginRight: "4px" }} />
                                      {useOnlyTripPricing
                                        ? "Add ticket type"
                                        : "Add pricing override"}
                                    </Button>
                                  )}
                                  {tripBoatPricingList.length > 0 &&
                                    isAddingTripBoatPricing && (
                                      <Text
                                        fontSize="xs"
                                        color="gray.500"
                                        mt={1}
                                      >
                                        To change a ticket type already in the
                                        list, edit it above instead of adding
                                        again.
                                      </Text>
                                    )}
                                </Box>
                              )}
                            </Box>
                          )
                        })}
                      </VStack>
                    ) : (
                      <Text mb={4}>No boats assigned to this trip yet.</Text>
                    )}

                    {/* Add boat form */}
                    {isAddingBoat ? (
                      <VStack
                        align="stretch"
                        gap={3}
                        mb={4}
                        p={3}
                        borderWidth="1px"
                        borderRadius="md"
                      >
                        <Field label="Select Boat" required>
                          <NativeSelect
                            value={selectedBoatId}
                            onChange={(
                              e: React.ChangeEvent<HTMLSelectElement>,
                            ) => setSelectedBoatId(e.target.value)}
                            disabled={mutation.isPending}
                          >
                            <option value="">Select a boat</option>
                            {boatsData.map((boat) => (
                              <option key={boat.id} value={boat.id}>
                                {boat.name} (Capacity: {boat.capacity})
                              </option>
                            ))}
                          </NativeSelect>
                        </Field>

                        <Field label="Custom Max Capacity (Optional)">
                          <Input
                            type="number"
                            value={maxCapacity || ""}
                            onChange={(e) =>
                              setMaxCapacity(
                                e.target.value
                                  ? Number.parseInt(e.target.value)
                                  : undefined,
                              )
                            }
                            min={1}
                          />
                        </Field>

                        <Flex justify="flex-end" gap={2}>
                          <Button
                            size="sm"
                            onClick={() => setIsAddingBoat(false)}
                          >
                            Cancel
                          </Button>
                          <Button
                            size="sm"
                            colorScheme="blue"
                            onClick={handleAddBoat}
                            disabled={!selectedBoatId}
                          >
                            Add Boat
                          </Button>
                        </Flex>
                      </VStack>
                    ) : (
                      <Button
                        onClick={() => setIsAddingBoat(true)}
                        size="sm"
                        mb={4}
                      >
                        <FiPlus style={{ marginRight: "4px" }} />
                        Add Boat
                      </Button>
                    )}
                  </Box>
                </Tabs.Content>

                {/* Merchandise tab */}
                <Tabs.Content value="pricing">
                  <VStack gap={3} align="stretch">
                    <Box>
                      <VStack align="stretch" gap={2}>
                        {tripMerchandiseList?.map((item) => (
                          <HStack
                            key={item.id}
                            justify="space-between"
                            p={3}
                            borderWidth="1px"
                            borderRadius="md"
                          >
                            <VStack align="start" flex={1}>
                              <Text fontWeight="medium">{item.name}</Text>
                              <HStack fontSize="sm" color="gray.500" gap={2} flexWrap="wrap">
                                <Text>${formatCents(item.price)} each</Text>
                                {item.variations_availability?.length ? (
                                  <Text>
                                    {item.variations_availability
                                      .map(
                                        (v) =>
                                          `${v.variant_value}: ${v.quantity_available}`,
                                      )
                                      .join(", ")}
                                  </Text>
                                ) : item.variant_options ? (
                                  <Text>
                                    Options: {item.variant_options} (qty{" "}
                                    {item.quantity_available})
                                  </Text>
                                ) : (
                                  <Text>Qty: {item.quantity_available}</Text>
                                )}
                              </HStack>
                            </VStack>
                            <IconButton
                              aria-label="Remove merchandise"
                              size="sm"
                              variant="ghost"
                              colorPalette="red"
                              onClick={() => handleRemoveMerchandise(item.id)}
                              disabled={deleteMerchandiseMutation.isPending}
                            >
                              <FiTrash2 />
                            </IconButton>
                          </HStack>
                        ))}
                        {(!tripMerchandiseList ||
                          tripMerchandiseList.length === 0) &&
                          !isAddingMerchandise && (
                            <Text color="gray.500" textAlign="center" py={3}>
                              No merchandise configured for this trip
                            </Text>
                          )}
                      </VStack>
                      {isAddingMerchandise ? (
                        <Box mt={2} p={3} borderWidth="1px" borderRadius="md">
                          <VStack gap={3}>
                            <HStack width="100%" align="stretch" gap={4}>
                              <Box
                                flex={1}
                                display="flex"
                                flexDirection="column"
                                minW={0}
                              >
                                <Text fontSize="sm" mb={1}>
                                  Catalog item
                                </Text>
                                {(() => {
                                  const selected = catalogMerchandise?.data?.find(
                                    (m) => m.id === merchandiseForm.merchandise_id,
                                  )
                                  if (
                                    !selected ||
                                    (selected.variations?.length ?? 0) > 0
                                  )
                                    return null
                                  return (
                                    <Text
                                      fontSize="xs"
                                      color="gray.500"
                                      mt={1}
                                    >
                                      No variants. Add variants in Merchandise
                                      catalog to show per-option availability.
                                    </Text>
                                  )
                                })()}
                                <Box flex={1} minHeight={2} />
                                <NativeSelect
                                  value={merchandiseForm.merchandise_id}
                                  onChange={(e) =>
                                    setMerchandiseForm({
                                      ...merchandiseForm,
                                      merchandise_id: e.target.value,
                                    })
                                  }
                                  placeholder="Select merchandise"
                                >
                                  {catalogMerchandise?.data?.map((m) => {
                                    const hasVariations =
                                      (m.variations?.length ?? 0) > 0
                                    const qtyLabel = hasVariations
                                      ? m.variations!
                                          .map(
                                            (v) =>
                                              `${v.variant_value}: ${v.quantity_total - v.quantity_sold}`,
                                          )
                                          .join(", ")
                                      : m.variant_options
                                        ? `${m.variant_options} (qty ${m.quantity_available})`
                                        : `qty ${m.quantity_available}`
                                    return (
                                      <option key={m.id} value={m.id}>
                                        {m.name} — ${formatCents(m.price)} (
                                        {qtyLabel})
                                      </option>
                                    )
                                  })}
                                </NativeSelect>
                              </Box>
                              <Box
                                flex={1}
                                display="flex"
                                flexDirection="column"
                                minW={0}
                              >
                                <Text fontSize="sm" mb={1}>
                                  Price override ($, optional)
                                </Text>
                                <Box flex={1} minHeight={2} />
                                <Input
                                  type="number"
                                  step="0.01"
                                  min={0}
                                  value={merchandiseForm.price_override}
                                  onChange={(e) =>
                                    setMerchandiseForm({
                                      ...merchandiseForm,
                                      price_override: e.target.value,
                                    })
                                  }
                                  placeholder="Use catalog price"
                                />
                              </Box>
                              <Box
                                flex={1}
                                display="flex"
                                flexDirection="column"
                                minW={0}
                              >
                                <Text fontSize="sm" mb={1}>
                                  Quantity override (optional)
                                </Text>
                                {catalogMerchandise?.data?.find(
                                  (m) => m.id === merchandiseForm.merchandise_id,
                                )?.variations?.length ? (
                                  <Text fontSize="xs" color="gray.500" mt={1}>
                                    Cap on total for this trip. Per-variant
                                    availability comes from catalog.
                                  </Text>
                                ) : null}
                                <Box flex={1} minHeight={2} />
                                <Input
                                  type="number"
                                  min={0}
                                  value={
                                    merchandiseForm.quantity_available_override
                                  }
                                  onChange={(e) =>
                                    setMerchandiseForm({
                                      ...merchandiseForm,
                                      quantity_available_override:
                                        e.target.value,
                                    })
                                  }
                                  placeholder={
                                    catalogMerchandise?.data?.find(
                                      (m) => m.id === merchandiseForm.merchandise_id,
                                    )?.variations?.length
                                      ? "Max total for trip"
                                      : "Use catalog qty"
                                  }
                                />
                              </Box>
                            </HStack>
                            <HStack width="100%" justify="flex-end">
                              <Button
                                size="sm"
                                onClick={() => setIsAddingMerchandise(false)}
                              >
                                Cancel
                              </Button>
                              <Button
                                size="sm"
                                colorPalette="blue"
                                onClick={handleAddMerchandise}
                                disabled={
                                  !merchandiseForm.merchandise_id ||
                                  createMerchandiseMutation.isPending
                                }
                              >
                                Add Merchandise
                              </Button>
                            </HStack>
                          </VStack>
                        </Box>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          mt={2}
                          onClick={() => setIsAddingMerchandise(true)}
                        >
                          <FiPlus style={{ marginRight: "4px" }} />
                          Add Merchandise
                        </Button>
                      )}
                    </Box>
                  </VStack>
                </Tabs.Content>
              </Tabs.Root>
            </DialogBody>

            <DialogFooter gap={2}>
              <ButtonGroup>
                <DialogActionTrigger asChild>
                  <Button
                    variant="subtle"
                    colorPalette="gray"
                    disabled={mutation.isPending}
                  >
                    Cancel
                  </Button>
                </DialogActionTrigger>
                <Button
                  variant="solid"
                  type="submit"
                  loading={mutation.isPending}
                  disabled={
                    !missionId ||
                    !departureTime ||
                    mutation.isPending
                  }
                >
                  Update
                </Button>
              </ButtonGroup>
            </DialogFooter>
          </form>
        </DialogContent>
      </DialogRoot>

      {/* Reassign passengers dialog */}
      <DialogRoot
        size="xs"
        placement="center"
        open={reassignFrom != null}
        onOpenChange={({ open }) => {
          if (!open) {
            setReassignFrom(null)
            setReassignToBoatId("")
            setReassignTypeMapping({})
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reassign passengers</DialogTitle>
          </DialogHeader>
          <DialogBody>
            {reassignFrom &&
              (() => {
                const from = reassignFrom
                const fromBoat = tripBoats.find((tb) => tb.boat_id === from.boat_id)
                const used: Record<string, number> =
                  fromBoat && "used_per_ticket_type" in fromBoat
                    ? (fromBoat as { used_per_ticket_type?: Record<string, number> })
                        .used_per_ticket_type ?? {}
                    : {}
                const sourceTypesWithQty = Object.entries(used).filter(
                  ([, qty]) => qty > 0,
                )
                const toBoat = tripBoats.find(
                  (tb) => tb.boat_id === reassignToBoatId,
                )
                const targetTypes: string[] =
                  toBoat && "pricing" in toBoat && Array.isArray((toBoat as { pricing?: { ticket_type: string }[] }).pricing)
                    ? ((toBoat as { pricing: { ticket_type: string }[] }).pricing ?? []).map(
                        (p) => p.ticket_type,
                      )
                    : []
                return (
                  <VStack align="stretch" gap={4}>
                    <Text>
                      Move {from.used} passenger(s) from{" "}
                      <strong>{from.boatName}</strong> to:
                    </Text>
                    <Field label="Target boat" required>
                      <NativeSelect
                        value={reassignToBoatId}
                        onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                          setReassignToBoatId(e.target.value)
                        }
                        disabled={isReassignSubmitting}
                      >
                        <option value="">Select a boat</option>
                        {tripBoats
                          .filter((tb) => tb.boat_id !== from.boat_id)
                          .map((tb) => {
                            const b = boatsMap.get(tb.boat_id)
                            const rem =
                              "remaining_capacity" in tb
                                ? (tb as { remaining_capacity: number })
                                    .remaining_capacity
                                : null
                            return (
                              <option key={tb.boat_id} value={tb.boat_id}>
                                {b?.name || "Unknown"}
                                {rem != null ? ` (${rem} spots left)` : ""}
                              </option>
                            )
                          })}
                      </NativeSelect>
                    </Field>
                    {reassignToBoatId &&
                      sourceTypesWithQty.length > 0 &&
                      targetTypes.length > 0 && (
                        <Field
                          label="Map ticket types"
                          helperText="Map each source boat ticket type to the target boat type it becomes."
                        >
                          <VStack align="stretch" gap={2}>
                            {sourceTypesWithQty.map(([srcType, qty]) => (
                              <Flex
                                key={srcType}
                                gap={2}
                                align="center"
                                wrap="wrap"
                              >
                                <Text fontSize="sm" flex="0 0 auto">
                                  {qty} × {srcType}
                                </Text>
                                <Text fontSize="sm" flex="0 0 auto">
                                  →
                                </Text>
                                <NativeSelect
                                  size="sm"
                                  value={reassignTypeMapping[srcType] ?? ""}
                                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                                    setReassignTypeMapping((prev) => ({
                                      ...prev,
                                      [srcType]: e.target.value,
                                    }))
                                  }
                                  disabled={isReassignSubmitting}
                                  style={{ minWidth: "10rem" }}
                                >
                                  <option value="">Select type</option>
                                  {targetTypes.map((tt) => (
                                    <option key={tt} value={tt}>
                                      {tt}
                                    </option>
                                  ))}
                                </NativeSelect>
                              </Flex>
                            ))}
                          </VStack>
                        </Field>
                      )}
                  </VStack>
                )
              })()}
          </DialogBody>
          <DialogFooter gap={2}>
            <Button
              variant="ghost"
              onClick={() => {
                setReassignFrom(null)
                setReassignToBoatId("")
                setReassignTypeMapping({})
              }}
              disabled={isReassignSubmitting}
            >
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={handleReassignConfirm}
              loading={isReassignSubmitting}
              disabled={!reassignCanSubmit}
            >
              Move passengers
            </Button>
          </DialogFooter>
        </DialogContent>
      </DialogRoot>
    </>
  )
}

export default EditTrip
