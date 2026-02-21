import {
  Box,
  Button,
  Flex,
  HStack,
  Heading,
  Input,
  Link,
  Separator,
  Text,
  Textarea,
  VStack,
} from "@chakra-ui/react"
import { zodResolver } from "@hookform/resolvers/zod"
import { useEffect } from "react"
import type { Resolver } from "react-hook-form"
import { Controller, useForm, useWatch } from "react-hook-form"
import { z } from "zod"

import { StarFleetTipLabel } from "@/components/Common/StarFleetTipLabel"
import { Checkbox } from "@/components/ui/checkbox"
import { Field } from "@/components/ui/field"
import { formatCents } from "@/utils"

import type { BookingStepData } from "../PublicBookingForm"

export const customerInfoSchema = z
  .object({
    first_name: z.string().min(1, "First name is required").max(255),
    last_name: z.string().min(1, "Last name is required").max(255),
    email: z
      .string()
      .min(1, "Email is required")
      .email("Enter a valid email address"),
    phone: z
      .string()
      .min(1, "Phone is required")
      .min(10, "Enter a valid phone number")
      .max(32),
    billing_address: z.string().min(1, "Billing address is required").max(500),
    special_requests: z.string().max(2000).optional().default(""),
    launch_updates_pref: z.boolean().default(false),
    terms_accepted: z.boolean().default(false),
  })
  .refine((data) => data.terms_accepted === true, {
    message: "You must accept the terms and conditions",
    path: ["terms_accepted"],
  })

export type CustomerInfo = z.infer<typeof customerInfoSchema>

function formatItemName(itemType: string): string {
  return itemType.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())
}

interface Step3CustomerInfoProps {
  bookingData: BookingStepData
  updateBookingData: (updates: Partial<BookingStepData>) => void
  onNext: () => void
  onBack: () => void
}

const defaultCustomerInfo: CustomerInfo = {
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  billing_address: "",
  special_requests: "",
  launch_updates_pref: false,
  terms_accepted: false,
}

const Step3CustomerInfo = ({
  bookingData,
  updateBookingData,
  onNext,
  onBack,
}: Step3CustomerInfoProps) => {
  const ci = bookingData.customerInfo

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<CustomerInfo>({
    resolver: zodResolver(customerInfoSchema) as Resolver<CustomerInfo>,
    mode: "onBlur",
    defaultValues: {
      first_name: ci?.first_name ?? defaultCustomerInfo.first_name,
      last_name: ci?.last_name ?? defaultCustomerInfo.last_name,
      email: ci?.email ?? defaultCustomerInfo.email,
      phone: ci?.phone ?? defaultCustomerInfo.phone,
      billing_address:
        ci?.billing_address ?? defaultCustomerInfo.billing_address,
      special_requests:
        ci?.special_requests ?? defaultCustomerInfo.special_requests,
      launch_updates_pref:
        ci?.launch_updates_pref ?? defaultCustomerInfo.launch_updates_pref,
      terms_accepted: ci?.terms_accepted ?? defaultCustomerInfo.terms_accepted,
    },
  })

  const watched = useWatch({ control })

  useEffect(() => {
    if (watched && typeof watched === "object" && "first_name" in watched) {
      updateBookingData({ customerInfo: watched as CustomerInfo })
    }
  }, [watched, updateBookingData])

  const handleNext = () => {
    handleSubmit(
      () => onNext(),
      () => {},
    )()
  }

  return (
    <Box>
      <Heading size="5xl" mb={8} fontWeight="200">
        Your Information
      </Heading>

      <Flex
        direction={{ base: "column", lg: "row" }}
        align="stretch"
        gap={6}
      >
        {/* Left Column - Customer Information */}
        <VStack gap={4} align="stretch" flex={1}>
          <Box>
            <Heading size="2xl" mb={4} fontWeight="200">
              Contact Information
            </Heading>
            <VStack gap={4} align="stretch">
              <Flex direction={{ base: "column", sm: "row" }} gap={4}>
                <Box flex={1}>
                  <Field
                    label="First Name"
                    required
                    invalid={!!errors.first_name}
                    errorText={errors.first_name?.message}
                  >
                    <Input
                      placeholder="Enter your first name"
                      {...register("first_name")}
                      borderColor="border.accent"
                    />
                  </Field>
                </Box>
                <Box flex={1}>
                  <Field
                    label="Last Name"
                    required
                    invalid={!!errors.last_name}
                    errorText={errors.last_name?.message}
                  >
                    <Input
                      placeholder="Enter your last name"
                      {...register("last_name")}
                      borderColor="border.accent"
                    />
                  </Field>
                </Box>
              </Flex>

              <Field
                label="Email Address"
                required
                invalid={!!errors.email}
                errorText={errors.email?.message}
              >
                <Input
                  type="email"
                  placeholder="Enter your email address"
                  {...register("email")}
                  borderColor="border.accent"
                />
              </Field>

              <Field
                label="Phone Number"
                required
                invalid={!!errors.phone}
                errorText={errors.phone?.message}
              >
                <Input
                  type="tel"
                  placeholder="Enter your phone number"
                  {...register("phone")}
                  borderColor="border.accent"
                />
              </Field>

              <Field
                label="Billing Address"
                required
                invalid={!!errors.billing_address}
                errorText={errors.billing_address?.message}
              >
                <Input
                  placeholder="Enter your billing address"
                  {...register("billing_address")}
                  borderColor="border.accent"
                />
              </Field>
            </VStack>
          </Box>

          <Box>
            <Heading size="sm" mb={4}>
              Special Requests
            </Heading>
            <Field
              invalid={!!errors.special_requests}
              errorText={errors.special_requests?.message}
            >
              <Textarea
                placeholder="Any special requests or accommodations needed..."
                {...register("special_requests")}
                rows={4}
                borderColor="border.accent"
              />
            </Field>
          </Box>

          <Box>
            <VStack gap={4} align="stretch">
              <Controller
                name="launch_updates_pref"
                control={control}
                render={({ field }) => (
                  <Checkbox
                    borderColor="border.accent"
                    checked={field.value}
                    onCheckedChange={({ checked }) =>
                      field.onChange(checked === true)
                    }
                  >
                    Send me updates about this launch
                  </Checkbox>
                )}
              />

              <Controller
                name="terms_accepted"
                control={control}
                render={({ field }) => (
                  <Field
                    invalid={!!errors.terms_accepted}
                    errorText={errors.terms_accepted?.message}
                  >
                    <Checkbox
                      borderColor="border.accent"
                      checked={field.value}
                      onCheckedChange={({ checked }) =>
                        field.onChange(checked === true)
                      }
                    >
                      I agree to the terms and conditions{" "}
                      <span style={{ color: "red" }}>*</span>
                    </Checkbox>
                  </Field>
                )}
              />

              <Text fontSize="xs" color="dark.text.secondary">
                By checking this box, you agree to our booking{" "}
                <Link
                  href="https://www.star-fleet.tours/details"
                  target="_blank"
                >
                  terms and conditions
                </Link>{" "}
                and{" "}
                <Link
                  href="https://www.star-fleet.tours/current"
                  target="_blank"
                >
                  scrub policy
                </Link>{" "}
                and acknowledge that you will receive booking confirmations and
                updates via email.
              </Text>
            </VStack>
          </Box>
        </VStack>

        {/* Right Column - Booking Summary */}
        <VStack gap={4} align="stretch" flex={1}>
          <Heading size="2xl" mb={4} fontWeight="200">
            Booking Summary
          </Heading>
          <VStack
            gap={3}
            align="stretch"
            px={5}
            py={4}
            bg="bg.accent"
            borderRadius="md"
          >
            <Heading size="xl" fontWeight="200">
              Selected Items
            </Heading>
            <Separator />
            <VStack gap={2} align="stretch" w="100%">
              {bookingData.selectedItems.map((item, index) => {
                const lineTotal = item.quantity * item.price_per_unit
                return (
                  <HStack
                    key={index}
                    justify="space-between"
                    align="baseline"
                    fontSize="sm"
                  >
                    <Flex gap={4} align="baseline" w="100%">
                      <Text fontWeight="medium">
                        {formatItemName(item.item_type)}
                        {item.variant_option
                          ? ` – ${item.variant_option}`
                          : ""}
                      </Text>
                      <Text
                        color="text.muted"
                        fontWeight="normal"
                        textAlign="start"
                      >
                        ({item.quantity} × ${formatCents(item.price_per_unit)})
                      </Text>
                    </Flex>
                    <Text fontWeight="medium">${formatCents(lineTotal)}</Text>
                  </HStack>
                )
              })}
            </VStack>
            <Separator />

            <HStack justify="space-between">
              <Text fontWeight="bold">Subtotal:</Text>
              <Text fontWeight="medium">
                ${formatCents(bookingData.subtotal)}
              </Text>
            </HStack>

            {bookingData.discount_amount > 0 && (
              <HStack justify="space-between">
                <Text fontWeight="bold">Discount:</Text>
                <Text fontWeight="medium">
                  -${formatCents(bookingData.discount_amount)}
                </Text>
              </HStack>
            )}

            <HStack justify="space-between">
              <Text fontWeight="bold">Tax:</Text>
              <Text fontWeight="medium">
                ${formatCents(bookingData.tax_amount)}
              </Text>
            </HStack>

            {bookingData.tip > 0 && (
              <HStack justify="space-between">
                <StarFleetTipLabel showColon />
                <Text fontWeight="medium">${formatCents(bookingData.tip)}</Text>
              </HStack>
            )}

            <HStack
              justify="space-between"
              pt={2}
              borderTop="1px"
              borderColor="gray.200"
            >
              <Text fontWeight="bold" fontSize="lg">
                Total:
              </Text>
              <Text fontWeight="bold" fontSize="lg">
                ${formatCents(bookingData.total)}
              </Text>
            </HStack>
          </VStack>
        </VStack>
      </Flex>

      {/* Navigation */}
      <Flex
        justify="space-between"
        mt={8}
        gap={4}
        direction={{ base: "column-reverse", sm: "row" }}
      >
        <Button variant="outline" onClick={onBack} w={{ base: "100%", sm: "auto" }}>
          Back
        </Button>
        <Button colorScheme="blue" onClick={handleNext} w={{ base: "100%", sm: "auto" }}>
          Continue to Review
        </Button>
      </Flex>
    </Box>
  )
}

export default Step3CustomerInfo
