import {
  type ApiError,
  BoatPricingService,
  type BoatUpdate,
  BoatsService,
} from "@/client"
import ProviderDropdown from "@/components/Common/ProviderDropdown"
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
import useCustomToast from "@/hooks/useCustomToast"
import type { Boat } from "@/types/boat"
import { formatCents, handleError } from "@/utils"
import {
  Box,
  Button,
  ButtonGroup,
  HStack,
  IconButton,
  Input,
  Text,
  VStack,
} from "@chakra-ui/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { Controller, type SubmitHandler, useForm } from "react-hook-form"
import { FiEdit, FiPlus, FiTrash2 } from "react-icons/fi"

interface EditBoatProps {
  boat: Boat
}

const EditBoat = ({ boat }: EditBoatProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const [isAddingPricing, setIsAddingPricing] = useState(false)
  const [editingPricingId, setEditingPricingId] = useState<string | null>(null)
  const [editPricingForm, setEditPricingForm] = useState({
    ticket_type: "",
    price: "",
    capacity: "",
  })
  const [pricingForm, setPricingForm] = useState({
    ticket_type: "",
    price: "",
    capacity: "",
  })
  const queryClient = useQueryClient()
  const { showSuccessToast } = useCustomToast()
  const contentRef = useRef(null)
  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors, isSubmitting },
  } = useForm<BoatUpdate>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      name: boat.name,
      capacity: boat.capacity,
      provider_id: boat.provider_id,
    },
  })

  // Sync form to current boat when dialog opens so we show latest data after refetch
  useEffect(() => {
    if (isOpen) {
      reset({
        name: boat.name,
        capacity: boat.capacity,
        provider_id: boat.provider_id,
      })
    }
  }, [isOpen, boat.name, boat.capacity, boat.provider_id, reset])

  const { data: boatPricingList = [], refetch: refetchBoatPricing } = useQuery({
    queryKey: ["boat-pricing", boat.id],
    queryFn: () => BoatPricingService.listBoatPricing({ boatId: boat.id }),
    enabled: isOpen && !!boat.id,
  })

  const mutation = useMutation({
    mutationFn: (data: BoatUpdate) =>
      BoatsService.updateBoat({
        boatId: boat.id,
        requestBody: data,
      }),
    onSuccess: () => {
      showSuccessToast("Boat updated successfully.")
      reset()
      setIsOpen(false)
    },
    onError: (err: ApiError) => {
      handleError(err)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["boats"] })
    },
  })

  const createPricingMutation = useMutation({
    mutationFn: (body: {
      ticket_type: string
      price: number
      capacity: number
    }) =>
      BoatPricingService.createBoatPricing({
        requestBody: {
          boat_id: boat.id,
          ticket_type: body.ticket_type,
          price: body.price,
          capacity: body.capacity,
        },
      }),
    onSuccess: () => {
      showSuccessToast("Ticket type added.")
      setPricingForm({ ticket_type: "", price: "", capacity: "" })
      setIsAddingPricing(false)
      refetchBoatPricing()
      queryClient.invalidateQueries({ queryKey: ["boat-pricing"] })
    },
    onError: (err: ApiError) => handleError(err),
  })

  const updatePricingMutation = useMutation({
    mutationFn: (body: {
      boatPricingId: string
      ticket_type?: string
      price?: number
      capacity?: number
    }) =>
      BoatPricingService.updateBoatPricing({
        boatPricingId: body.boatPricingId,
        requestBody: {
          ticket_type: body.ticket_type,
          price: body.price,
          ...(body.capacity !== undefined ? { capacity: body.capacity } : {}),
        },
      }),
    onSuccess: () => {
      showSuccessToast("Ticket type updated. Existing bookings updated.")
      setEditingPricingId(null)
      setEditPricingForm({ ticket_type: "", price: "", capacity: "" })
      refetchBoatPricing()
      queryClient.invalidateQueries({ queryKey: ["boat-pricing"] })
      queryClient.invalidateQueries({ queryKey: ["bookings"] })
    },
    onError: (err: ApiError) => handleError(err),
  })

  const deletePricingMutation = useMutation({
    mutationFn: (boatPricingId: string) =>
      BoatPricingService.deleteBoatPricing({ boatPricingId }),
    onSuccess: () => {
      showSuccessToast("Ticket type removed.")
      refetchBoatPricing()
      queryClient.invalidateQueries({ queryKey: ["boat-pricing"] })
    },
    onError: (err: ApiError) => handleError(err),
  })

  const handleAddPricing = () => {
    const priceDollars = Number.parseFloat(pricingForm.price)
    const cap = Number.parseInt(pricingForm.capacity, 10)
    if (
      !pricingForm.ticket_type.trim() ||
      Number.isNaN(priceDollars) ||
      Number.isNaN(cap) ||
      cap < 0
    )
      return
    createPricingMutation.mutate({
      ticket_type: pricingForm.ticket_type.trim(),
      price: Math.round(priceDollars * 100),
      capacity: cap,
    })
  }

  const onSubmit: SubmitHandler<BoatUpdate> = async (data) => {
    mutation.mutate(data)
  }

  return (
    <DialogRoot
      size={{ base: "xs", md: "md" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" color="dark.accent.primary">
          <FiEdit fontSize="16px" />
          Edit
        </Button>
      </DialogTrigger>

      <DialogContent ref={contentRef}>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogCloseTrigger />
          <DialogHeader>
            <DialogTitle>Edit Boat</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Text mb={4}>Update the boat details below.</Text>
            <VStack gap={4}>
              <Field
                invalid={!!errors.name}
                errorText={errors.name?.message}
                label="Name"
                required
              >
                <Input
                  id="name"
                  {...register("name", {
                    minLength: { value: 1, message: "Name cannot be empty" },
                    maxLength: {
                      value: 255,
                      message: "Name cannot exceed 255 characters",
                    },
                  })}
                  placeholder="Name"
                  type="text"
                />
              </Field>

              <Field
                invalid={!!errors.capacity}
                errorText={errors.capacity?.message}
                label="Capacity"
                required
              >
                <Controller
                  name="capacity"
                  control={control}
                  rules={{
                    min: { value: 1, message: "Capacity must be at least 1" },
                  }}
                  render={({ field }) => (
                    <Input
                      id="capacity"
                      type="number"
                      value={field.value ?? ""}
                      onChange={(e) =>
                        field.onChange(Number.parseInt(e.target.value) || 1)
                      }
                      min={1}
                      disabled={isSubmitting}
                      placeholder="Capacity"
                    />
                  )}
                />
              </Field>

              <Field
                invalid={!!errors.provider_id}
                errorText={errors.provider_id?.message}
                label="Provider"
                required
              >
                <Controller
                  name="provider_id"
                  control={control}
                  render={({ field }) => (
                    <ProviderDropdown
                      id="provider_id"
                      value={field.value ? String(field.value) : ""}
                      onChange={field.onChange}
                      isDisabled={isSubmitting}
                      portalRef={contentRef}
                    />
                  )}
                />
              </Field>

              <Box width="100%">
                <Text fontWeight="bold" mb={2}>
                  Ticket types (default pricing)
                </Text>
                <Text fontSize="sm" color="gray.400" mb={2}>
                  Default ticket types and prices for this boat. Trips can
                  override per boat.
                </Text>
                {isAddingPricing ? (
                  <VStack
                    align="stretch"
                    gap={2}
                    mb={3}
                    p={3}
                    borderWidth="1px"
                    borderRadius="md"
                  >
                    <HStack width="100%" gap={2} flexWrap="wrap">
                      <Box flex={1} minW="120px">
                        <Text fontSize="sm" mb={1}>
                          Ticket type
                        </Text>
                        <Input
                          value={pricingForm.ticket_type}
                          onChange={(e) =>
                            setPricingForm({
                              ...pricingForm,
                              ticket_type: e.target.value,
                            })
                          }
                          placeholder="e.g. Adult, Child"
                        />
                      </Box>
                      <Box flex={1} minW="80px">
                        <Text fontSize="sm" mb={1}>
                          Price ($)
                        </Text>
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          value={pricingForm.price}
                          onChange={(e) =>
                            setPricingForm({
                              ...pricingForm,
                              price: e.target.value,
                            })
                          }
                          placeholder="0.00"
                        />
                      </Box>
                      <Box flex={1} minW="80px">
                        <Text fontSize="sm" mb={1}>
                          Capacity
                        </Text>
                        <Input
                          type="number"
                          min="0"
                          value={pricingForm.capacity}
                          onChange={(e) =>
                            setPricingForm({
                              ...pricingForm,
                              capacity: e.target.value,
                            })
                          }
                          placeholder="0"
                        />
                      </Box>
                    </HStack>
                    <Text fontSize="xs" color="gray.500">
                      Sum of ticket-type capacities must not exceed boat
                      capacity ({boat.capacity}).
                    </Text>
                    <HStack width="100%" justify="flex-end">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setIsAddingPricing(false)}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleAddPricing}
                        loading={createPricingMutation.isPending}
                        disabled={
                          !pricingForm.ticket_type.trim() ||
                          !pricingForm.price ||
                          !pricingForm.capacity ||
                          Number.isNaN(Number.parseFloat(pricingForm.price)) ||
                          Number.isNaN(
                            Number.parseInt(pricingForm.capacity, 10),
                          ) ||
                          Number.parseInt(pricingForm.capacity, 10) < 0
                        }
                      >
                        Add
                      </Button>
                    </HStack>
                  </VStack>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    mb={2}
                    onClick={() => {
                      setEditingPricingId(null)
                      setIsAddingPricing(true)
                    }}
                  >
                    <FiPlus style={{ marginRight: "4px" }} />
                    Add ticket type
                  </Button>
                )}
                <VStack align="stretch" gap={2}>
                  {boatPricingList.map((p) =>
                    editingPricingId === p.id ? (
                      <VStack
                        key={p.id}
                        align="stretch"
                        gap={2}
                        p={3}
                        borderWidth="1px"
                        borderRadius="md"
                      >
                        <HStack width="100%" gap={2} flexWrap="wrap">
                          <Box flex={1} minW="120px">
                            <Text fontSize="sm" mb={1}>
                              Ticket type
                            </Text>
                            <Input
                              value={editPricingForm.ticket_type}
                              onChange={(e) =>
                                setEditPricingForm((prev) => ({
                                  ...prev,
                                  ticket_type: e.target.value,
                                }))
                              }
                              placeholder="e.g. Adult, Child"
                            />
                          </Box>
                          <Box flex={1} minW="80px">
                            <Text fontSize="sm" mb={1}>
                              Price ($)
                            </Text>
                            <Input
                              type="number"
                              step="0.01"
                              min="0"
                              value={editPricingForm.price}
                              onChange={(e) =>
                                setEditPricingForm((prev) => ({
                                  ...prev,
                                  price: e.target.value,
                                }))
                              }
                            />
                          </Box>
                          <Box flex={1} minW="80px">
                            <Text fontSize="sm" mb={1}>
                              Capacity
                            </Text>
                            <Input
                              type="number"
                              min="0"
                              value={editPricingForm.capacity}
                              onChange={(e) =>
                                setEditPricingForm((prev) => ({
                                  ...prev,
                                  capacity: e.target.value,
                                }))
                              }
                            />
                          </Box>
                        </HStack>
                        <HStack width="100%" justify="flex-end">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setEditingPricingId(null)
                              setEditPricingForm({
                                ticket_type: "",
                                price: "",
                                capacity: "",
                              })
                            }}
                          >
                            Cancel
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => {
                              const ticketType =
                                editPricingForm.ticket_type.trim()
                              const priceDollars = Number.parseFloat(
                                editPricingForm.price,
                              )
                              const cap = Number.parseInt(
                                editPricingForm.capacity,
                                10,
                              )
                              if (
                                ticketType &&
                                !Number.isNaN(priceDollars) &&
                                !Number.isNaN(cap) &&
                                cap >= 0
                              ) {
                                updatePricingMutation.mutate({
                                  boatPricingId: p.id,
                                  ticket_type: ticketType,
                                  price: Math.round(priceDollars * 100),
                                  capacity: cap,
                                })
                              }
                            }}
                            loading={updatePricingMutation.isPending}
                          >
                            Save
                          </Button>
                        </HStack>
                      </VStack>
                    ) : (
                      <HStack
                        key={p.id}
                        justify="space-between"
                        p={2}
                        borderWidth="1px"
                        borderRadius="md"
                      >
                        <HStack>
                          <Text fontWeight="medium">{p.ticket_type}</Text>
                          <Text fontSize="sm" color="gray.400">
                            ${formatCents(p.price)} ({p.capacity} seats)
                          </Text>
                        </HStack>
                        <HStack>
                          <IconButton
                            aria-label="Edit ticket type"
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setIsAddingPricing(false)
                              setEditingPricingId(p.id)
                              setEditPricingForm({
                                ticket_type: p.ticket_type,
                                price: (p.price / 100).toFixed(2),
                                capacity: String(p.capacity),
                              })
                            }}
                            disabled={
                              updatePricingMutation.isPending ||
                              deletePricingMutation.isPending
                            }
                          >
                            <FiEdit />
                          </IconButton>
                          <IconButton
                            aria-label="Remove ticket type"
                            size="sm"
                            variant="ghost"
                            colorPalette="red"
                            onClick={() => deletePricingMutation.mutate(p.id)}
                            disabled={deletePricingMutation.isPending}
                          >
                            <FiTrash2 />
                          </IconButton>
                        </HStack>
                      </HStack>
                    ),
                  )}
                  {boatPricingList.length === 0 && !isAddingPricing && (
                    <Text fontSize="sm" color="gray.500" py={2}>
                      No ticket types. Add trip boats and pricing on each trip,
                      or set defaults here.
                    </Text>
                  )}
                </VStack>
              </Box>
            </VStack>
          </DialogBody>

          <DialogFooter gap={2}>
            <ButtonGroup>
              <DialogActionTrigger asChild>
                <Button
                  variant="subtle"
                  colorPalette="gray"
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
              </DialogActionTrigger>
              <Button variant="solid" type="submit" loading={isSubmitting}>
                Save
              </Button>
            </ButtonGroup>
          </DialogFooter>
        </form>
      </DialogContent>
    </DialogRoot>
  )
}

export default EditBoat
