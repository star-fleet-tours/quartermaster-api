import {
  type ApiError,
  type BoatCreate,
  BoatPricingService,
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
} from "@/components/ui/dialog"
import { Field } from "@/components/ui/field"
import useCustomToast from "@/hooks/useCustomToast"
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
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useRef, useState } from "react"
import { Controller, type SubmitHandler, useForm } from "react-hook-form"
import { FiPlus, FiTrash2 } from "react-icons/fi"

interface AddBoatProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

type AddBoatForm = Omit<BoatCreate, "capacity"> & { capacity?: number }

type PendingPricingRow = { ticket_type: string; price: string; capacity: string }

const AddBoat = ({ isOpen, onClose, onSuccess }: AddBoatProps) => {
  const contentRef = useRef(null)
  const queryClient = useQueryClient()
  const { showSuccessToast } = useCustomToast()
  const [isAddingPricing, setIsAddingPricing] = useState(false)
  const [pricingForm, setPricingForm] = useState({
    ticket_type: "",
    price: "",
    capacity: "",
  })
  const [pendingPricing, setPendingPricing] = useState<PendingPricingRow[]>([])

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors, isSubmitting },
  } = useForm<AddBoatForm>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      name: "",
      capacity: undefined,
      provider_id: "",
    },
  })

  const createBoatMutation = useMutation({
    mutationFn: (data: BoatCreate) =>
      BoatsService.createBoat({
        requestBody: data,
      }),
    onError: (err: ApiError) => handleError(err),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["boats"] })
    },
  })

  const onSubmit: SubmitHandler<AddBoatForm> = async (data) => {
    if (data.capacity == null || data.capacity < 1) return
    const boatPayload: BoatCreate = {
      name: data.name,
      capacity: data.capacity,
      provider_id: data.provider_id,
    }
    const totalPendingCapacity = pendingPricing.reduce((sum, row) => {
      const cap = Number.parseInt(row.capacity, 10)
      if (
        !row.ticket_type.trim() ||
        Number.isNaN(Number.parseFloat(row.price)) ||
        Number.isNaN(cap) ||
        cap < 0
      )
        return sum
      return sum + cap
    }, 0)
    if (totalPendingCapacity > boatPayload.capacity) {
      handleError({
        body: {
          detail: `Sum of ticket-type capacities (${totalPendingCapacity}) would exceed boat capacity (${boatPayload.capacity})`,
        },
      } as ApiError)
      return
    }
    createBoatMutation.mutate(boatPayload, {
      onSuccess: async (boat) => {
        let pricingFailed = false
        for (const row of pendingPricing) {
          const priceCents = Math.round(Number.parseFloat(row.price) * 100)
          const cap = Number.parseInt(row.capacity, 10)
          if (
            !row.ticket_type.trim() ||
            Number.isNaN(priceCents) ||
            Number.isNaN(cap) ||
            cap < 0
          )
            continue
          try {
            await BoatPricingService.createBoatPricing({
              requestBody: {
                boat_id: boat.id,
                ticket_type: row.ticket_type.trim(),
                price: priceCents,
                capacity: cap,
              },
            })
          } catch (err) {
            handleError(err as ApiError)
            pricingFailed = true
            queryClient.invalidateQueries({ queryKey: ["boats"] })
            break
          }
        }
        if (pricingFailed) return
        queryClient.invalidateQueries({ queryKey: ["boat-pricing"] })
        showSuccessToast("Boat created successfully.")
        reset()
        setPendingPricing([])
        setPricingForm({ ticket_type: "", price: "", capacity: "" })
        setIsAddingPricing(false)
        onSuccess()
        onClose()
      },
    })
  }

  const addPendingPricing = () => {
    const priceDollars = Number.parseFloat(pricingForm.price)
    const cap = Number.parseInt(pricingForm.capacity, 10)
    if (
      !pricingForm.ticket_type.trim() ||
      Number.isNaN(priceDollars) ||
      Number.isNaN(cap) ||
      cap < 0
    )
      return
    setPendingPricing((prev) => [
      ...prev,
      {
        ticket_type: pricingForm.ticket_type.trim(),
        price: pricingForm.price,
        capacity: pricingForm.capacity,
      },
    ])
    setPricingForm({ ticket_type: "", price: "", capacity: "" })
    setIsAddingPricing(false)
  }

  const removePendingPricing = (index: number) => {
    setPendingPricing((prev) => prev.filter((_, i) => i !== index))
  }

  return (
    <DialogRoot
      size={{ base: "xs", md: "md" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => !open && onClose()}
    >
      <DialogContent ref={contentRef}>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogHeader>
            <DialogTitle>Add Boat</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Text mb={4}>Add a new boat by filling out the form below.</Text>
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
                    required: "Name is required",
                    minLength: { value: 1, message: "Name is required" },
                    maxLength: {
                      value: 255,
                      message: "Name cannot exceed 255 characters",
                    },
                  })}
                  placeholder="Name"
                  type="text"
                  disabled={createBoatMutation.isPending}
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
                    required: "Capacity is required",
                    validate: (value) => {
                      if (value === undefined || value === null) return "Capacity is required"
                      if (typeof value !== "number" || !Number.isInteger(value)) return "Capacity must be a number"
                      if (value < 1) return "Capacity must be at least 1"
                      return true
                    },
                  }}
                  render={({ field }) => (
                    <Input
                      id="capacity"
                      type="number"
                      value={field.value === undefined ? "" : field.value}
                      onChange={(e) => {
                        const v = e.target.value
                        if (v === "") {
                          field.onChange(undefined)
                        } else {
                          const n = Number.parseInt(v, 10)
                          if (!Number.isNaN(n)) field.onChange(n)
                        }
                      }}
                      min={1}
                      disabled={isSubmitting || createBoatMutation.isPending}
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
                  rules={{ required: "Provider is required" }}
                  render={({ field }) => (
                    <ProviderDropdown
                      id="provider_id"
                      value={field.value || ""}
                      onChange={field.onChange}
                      isDisabled={isSubmitting || createBoatMutation.isPending}
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
                  Optional. Add default ticket types and prices for this boat.
                  You can also add them after creating the boat.
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
                        onClick={addPendingPricing}
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
                    onClick={() => setIsAddingPricing(true)}
                  >
                    <FiPlus style={{ marginRight: "4px" }} />
                    Add ticket type
                  </Button>
                )}
                <VStack align="stretch" gap={2}>
                  {pendingPricing.map((p, index) => (
                    <HStack
                      key={index}
                      justify="space-between"
                      p={2}
                      borderWidth="1px"
                      borderRadius="md"
                    >
                      <HStack>
                        <Text fontWeight="medium">{p.ticket_type}</Text>
                        <Text fontSize="sm" color="gray.400">
                          ${formatCents(Math.round(Number.parseFloat(p.price) * 100))} (
                          {p.capacity} seats)
                        </Text>
                      </HStack>
                      <IconButton
                        aria-label="Remove ticket type"
                        size="sm"
                        variant="ghost"
                        colorPalette="red"
                        onClick={() => removePendingPricing(index)}
                        disabled={createBoatMutation.isPending}
                      >
                        <FiTrash2 />
                      </IconButton>
                    </HStack>
                  ))}
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
                  disabled={isSubmitting || createBoatMutation.isPending}
                >
                  Cancel
                </Button>
              </DialogActionTrigger>
              <Button
                variant="solid"
                type="submit"
                loading={isSubmitting || createBoatMutation.isPending}
              >
                Add Boat
              </Button>
            </ButtonGroup>
          </DialogFooter>
        </form>
        <DialogCloseTrigger />
      </DialogContent>
    </DialogRoot>
  )
}

export default AddBoat
