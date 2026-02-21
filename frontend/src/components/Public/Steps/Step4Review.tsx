import {
  Box,
  Button,
  Flex,
  HStack,
  Heading,
  Separator,
  Text,
  VStack,
} from "@chakra-ui/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useSearch } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import type { MutableRefObject } from "react"

import { StarFleetTipLabel } from "@/components/Common/StarFleetTipLabel"
import { formatCents } from "@/utils"
import {
  type BookingCreate,
  BookingsService,
  PaymentsService,
} from "../../../client"

import PaymentForm from "../PaymentForm"
import type { BookingResult, BookingStepData } from "../PublicBookingForm"
import StripeProvider from "../StripeProvider"
import { customerInfoSchema } from "./Step3CustomerInfo"

const CONFIRMED_STATUSES = ["confirmed", "checked_in", "completed"]

interface Step4ReviewProps {
  bookingData: BookingStepData
  onBack: () => void
  /** Booking + payment result (from parent). Set as soon as draft and payment intent are ready. */
  bookingResult: BookingResult | null
  /** Called when draft booking and payment intent are ready. */
  onBookingReady: (result: BookingResult) => void
  /** When resuming by code, called with the loaded booking so parent can pre-fill form. */
  onResumeBookingLoaded?: (booking: BookingResult["booking"]) => void
  /** When true, do not overwrite form (user already had form filled and may have edited). */
  skipHydrateForm?: boolean
  /** Confirmation code from URL; when set, resume existing booking instead of creating. */
  urlCode?: string
  /** Parent ref: survives remounts (e.g. Strict Mode) so we don't create booking twice. */
  createBookingStartedRef: MutableRefObject<boolean>
  /** Access code's discount_code.id (early_bird); use this for create payload so Step 2 discount does not overwrite. */
  accessCodeDiscountCodeId?: string | null
}

const Step4Review = ({
  bookingData,
  onBack,
  bookingResult,
  onBookingReady,
  onResumeBookingLoaded,
  skipHydrateForm,
  urlCode,
  createBookingStartedRef,
  accessCodeDiscountCodeId,
}: Step4ReviewProps) => {
  const navigate = useNavigate()
  const search = useSearch({ from: "/book" })
  const queryClient = useQueryClient()
  const [isBookingSuccessful, setIsBookingSuccessful] = useState(false)
  const [customerInfoInvalid, setCustomerInfoInvalid] = useState(false)
  const bookingWithPayment = bookingResult
  const createStartedRef = useRef(false)

  // Generate a random confirmation code
  const generateConfirmationCode = () => {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    let code = ""
    for (let i = 0; i < 8; i++) {
      code += chars.charAt(Math.floor(Math.random() * chars.length))
    }
    return code
  }

  const loadByCodeMutation = useMutation({
    mutationFn: async (code: string) => {
      const booking = await BookingsService.getBookingByConfirmationCode({
        confirmationCode: code,
      })
      return { booking }
    },
    onSuccess: async ({ booking }, code) => {
      const bookingStatus = (booking.booking_status ?? "") as string
      if (CONFIRMED_STATUSES.includes(bookingStatus)) {
        navigate({ to: "/bookings", search: { code } })
        return
      }
      if (bookingStatus === "cancelled") {
        navigate({
          to: "/book",
          search: { discount: search.discount, access: search.access },
          replace: true,
        })
        return
      }
      try {
        let bookingToUse = booking
        if (!skipHydrateForm) {
          onResumeBookingLoaded?.(booking)
        } else {
          const parsed = customerInfoSchema.safeParse(bookingData.customerInfo)
          if (!parsed.success) {
            setCustomerInfoInvalid(true)
            return
          }
          setCustomerInfoInvalid(false)
          // User edited the form; persist to backend so payment/confirmation use updated details
          const updated = await BookingsService.bookingPublicUpdateDraftBooking(
            {
              confirmationCode: code,
              requestBody: {
                first_name: bookingData.customerInfo.first_name || undefined,
                last_name: bookingData.customerInfo.last_name || undefined,
                user_email: bookingData.customerInfo.email || undefined,
                user_phone: bookingData.customerInfo.phone || undefined,
                billing_address:
                  bookingData.customerInfo.billing_address || undefined,
                special_requests:
                  bookingData.customerInfo.special_requests || undefined,
                launch_updates_pref:
                  bookingData.customerInfo.launch_updates_pref ?? undefined,
                tip_amount: bookingData.tip ?? undefined,
                subtotal: bookingData.subtotal,
                discount_amount: bookingData.discount_amount,
                tax_amount: bookingData.tax_amount,
                total_amount: bookingData.total,
              },
            },
          )
          bookingToUse = updated
        }
        const totalCents = bookingToUse.total_amount ?? 0
        if (bookingStatus === "draft" && totalCents < 50) {
          await BookingsService.confirmFreeBooking({
            confirmationCode: code,
          })
          navigate({ to: "/bookings", search: { code } })
          return
        }
        const paymentData =
          bookingStatus === "draft"
            ? await BookingsService.initializePayment({
                confirmationCode: code,
              })
            : await BookingsService.resumePayment({
                confirmationCode: code,
              })
        onBookingReady({ booking: bookingToUse, paymentData })
      } catch {
        navigate({
          to: "/book",
          search: { discount: search.discount, access: search.access },
          replace: true,
        })
      }
    },
    onError: () => {
      navigate({
        to: "/book",
        search: { discount: search.discount, access: search.access },
        replace: true,
      })
    },
  })

  const createBookingMutation = useMutation({
    mutationFn: async (data: { bookingData: BookingStepData }) => {
      const { bookingData } = data

      const bookingCreate: BookingCreate = {
        first_name: bookingData.customerInfo.first_name,
        last_name: bookingData.customerInfo.last_name,
        user_email: bookingData.customerInfo.email,
        user_phone: bookingData.customerInfo.phone,
        billing_address: bookingData.customerInfo.billing_address || "",
        confirmation_code: generateConfirmationCode(),
        items: bookingData.selectedItems.map((item) => ({
          trip_id: item.trip_id,
          boat_id: bookingData.selectedBoatId,
          item_type: item.item_type,
          quantity: item.quantity,
          price_per_unit: item.price_per_unit,
          trip_merchandise_id: item.trip_merchandise_id,
          variant_option: item.variant_option,
        })),
        subtotal: bookingData.subtotal,
        discount_amount: bookingData.discount_amount,
        tax_amount: bookingData.tax_amount,
        tip_amount: bookingData.tip,
        total_amount: bookingData.total,
        special_requests: bookingData.customerInfo.special_requests || "",
        launch_updates_pref:
          bookingData.customerInfo.launch_updates_pref ?? false,
        discount_code_id:
          accessCodeDiscountCodeId ?? bookingData.discount_code_id,
      }

      const booking = await BookingsService.createBooking({
        requestBody: bookingCreate,
      })
      if (bookingData.total < 50) {
        await BookingsService.confirmFreeBooking({
          confirmationCode: booking.confirmation_code,
        })
        return { booking, free: true as const }
      }
      const paymentData = await BookingsService.initializePayment({
        confirmationCode: booking.confirmation_code,
      })
      return { booking, paymentData }
    },
    onSuccess: (data) => {
      if ("free" in data && data.free) {
        navigate({ to: "/bookings", search: { code: data.booking.confirmation_code } })
        return
      }
      onBookingReady({ booking: data.booking, paymentData: data.paymentData! })
      // Do not navigate here: parent state (bookingResult) is async; navigating now would
      // re-render with urlCode set and bookingResult null, triggering loadByCode and "Preparing...".
      // Code is added to URL in the effect below when we have bookingResult.
    },
    onError: (error) => {
      createStartedRef.current = false
      createBookingStartedRef.current = false
      console.error("Failed to create booking:", error)
    },
  })

  const completeBookingMutation = useMutation({
    mutationFn: async ({
      paymentIntentId,
      confirmationCode,
    }: {
      paymentIntentId: string
      confirmationCode: string
    }) => {
      await PaymentsService.verifyPayment({ paymentIntentId })
      return { paymentIntentId, confirmationCode }
    },
    onSuccess: (data) => {
      setIsBookingSuccessful(true)
      queryClient.invalidateQueries({ queryKey: ["bookings"] })
      setTimeout(() => {
        navigate({
          to: "/bookings",
          search: { code: data.confirmationCode },
        })
      }, 3000)
    },
    onError: (error) => {
      console.error("Failed to process payment success:", error)
    },
  })

  const handlePaymentSuccess = (paymentIntentId: string) => {
    const confirmationCode = bookingWithPayment?.booking?.confirmation_code
    if (!confirmationCode) return
    completeBookingMutation.mutate({ paymentIntentId, confirmationCode })
  }

  const handlePaymentError = (error: Error) => {
    console.error("Payment failed:", error.message)
  }

  // When restored from bfcache (mobile reload), re-fetch booking by code. If confirmed, navigate to
  // confirmation. Fixes stuck "Processing Payment" on mobile where reload restores frozen state.
  useEffect(() => {
    const onPageShow = (e: PageTransitionEvent) => {
      if (!e.persisted || !urlCode) return
      loadByCodeMutation.mutate(urlCode)
    }
    window.addEventListener("pageshow", onPageShow)
    return () => window.removeEventListener("pageshow", onPageShow)
  }, [urlCode])

  // When we have bookingResult but URL has no code, add code for bookmarking (after create success).
  useEffect(() => {
    const code = bookingResult?.booking?.confirmation_code
    if (code && search.code !== code) {
      navigate({
        to: "/book",
        search: {
          discount: search.discount,
          access: search.access,
          code,
        },
        replace: true,
      })
    }
  }, [
    bookingResult?.booking?.confirmation_code,
    search.code,
    search.discount,
    search.access,
    navigate,
  ])

  // If URL has code: load existing booking and resume/init payment. Otherwise create new (once) and set code in URL.
  // Parent ref survives remounts (Strict Mode) so we don't create twice.
  useEffect(() => {
    if (bookingResult) return
    if (urlCode) {
      createStartedRef.current = false
      createBookingStartedRef.current = false
      if (!loadByCodeMutation.isPending) {
        loadByCodeMutation.mutate(urlCode)
      }
      return
    }
    if (
      createStartedRef.current ||
      createBookingStartedRef.current ||
      createBookingMutation.isPending
    )
      return
    const parsed = customerInfoSchema.safeParse(bookingData.customerInfo)
    if (!parsed.success) {
      setCustomerInfoInvalid(true)
      return
    }
    setCustomerInfoInvalid(false)
    createStartedRef.current = true
    createBookingStartedRef.current = true
    createBookingMutation.mutate({ bookingData })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- urlCode, bookingResult drive flow; re-validate when customerInfo changes (e.g. user returned from Step 3)
  }, [urlCode, bookingResult, bookingData.customerInfo])

  const isPending =
    createBookingMutation.isPending || loadByCodeMutation.isPending

  // Customer info failed validation (e.g. state corrupted or user resumed with incomplete data). Ask to go back.
  if (customerInfoInvalid && !bookingResult) {
    return (
      <VStack gap={6} align="stretch">
        <Box
          p={4}
          bg="orange.50"
          border="1px"
          borderColor="orange.200"
          borderRadius="md"
        >
          <Heading size="sm" color="orange.800" mb={2}>
            Information incomplete or invalid
          </Heading>
          <Text color="orange.700" fontSize="sm" mb={4}>
            Please go back and complete your contact and billing details before
            continuing.
          </Text>
          <Button variant="outline" onClick={onBack}>
            Back to your information
          </Button>
        </Box>
      </VStack>
    )
  }

  // Once we have bookingResult (from create or loadByCode), show payment form even if
  // something is still pending (e.g. loadByCode was triggered by URL update before parent re-rendered).
  if (isPending && !bookingResult) {
    const isFree = bookingData.total < 50
    return (
      <VStack gap={6} align="stretch">
        <Box
          p={6}
          bg="blue.50"
          border="1px"
          borderColor="blue.200"
          borderRadius="md"
          textAlign="center"
        >
          <Text color="blue.800" fontWeight="medium">
            {isFree ? "Confirming your free booking..." : "Preparing your booking..."}
          </Text>
          <Text color="blue.700" fontSize="sm" mt={2}>
            {isFree
              ? "Please wait."
              : "Please wait while we set up your payment."}
          </Text>
        </Box>
      </VStack>
    )
  }

  // Show error message if booking creation or payment verification failed (not loadByCode: that clears URL and retries)
  if (createBookingMutation.isError || completeBookingMutation.isError) {
    const apiDetail =
      createBookingMutation.isError &&
      createBookingMutation.error &&
      "body" in createBookingMutation.error &&
      createBookingMutation.error.body &&
      typeof createBookingMutation.error.body === "object" &&
      "detail" in createBookingMutation.error.body
        ? (() => {
            const d = (
              createBookingMutation.error.body as { detail?: string | string[] }
            ).detail
            return typeof d === "string"
              ? d
              : Array.isArray(d)
                ? d[0]
                : undefined
          })()
        : undefined
    const errorMessage = createBookingMutation.isError
      ? apiDetail ??
        "There was an error creating your booking. Please try again or contact FleetCommand@Star-Fleet.Tours if the problem persists."
      : "Payment was successful but we couldn't confirm your booking. Please contact FleetCommand@Star-Fleet.Tours for assistance."

    const canRetryVerification =
      completeBookingMutation.isError &&
      bookingWithPayment?.booking?.confirmation_code &&
      bookingWithPayment?.paymentData?.payment_intent_id

    const handleRetryVerification = () => {
      if (!canRetryVerification) return
      completeBookingMutation.mutate({
        paymentIntentId: bookingWithPayment.paymentData.payment_intent_id,
        confirmationCode: bookingWithPayment.booking.confirmation_code,
      })
    }

    return (
      <VStack gap={6} align="stretch">
        <Box
          p={4}
          bg="red.50"
          border="1px"
          borderColor="red.200"
          borderRadius="md"
        >
          <Text color="red.800" fontWeight="medium">
            {createBookingMutation.isError
              ? "Booking Creation Failed"
              : "Payment Verification Failed"}
          </Text>
          <Text color="red.700" fontSize="sm" mt={2}>
            {errorMessage}
          </Text>
        </Box>
        <HStack gap={2}>
          {canRetryVerification && (
            <Button
              onClick={handleRetryVerification}
              colorScheme="blue"
              loading={completeBookingMutation.isPending}
              loadingText="Verifying..."
            >
              Retry Verification
            </Button>
          )}
          <Button onClick={onBack} variant="outline">
            Back to Review
          </Button>
        </HStack>
      </VStack>
    )
  }

  // Show success message if booking was successful
  if (isBookingSuccessful) {
    return (
      <VStack gap={6} align="stretch">
        <Box
          p={6}
          bg="green.50"
          border="1px"
          borderColor="green.200"
          borderRadius="md"
          textAlign="center"
        >
          <Heading size="md" color="green.800" mb={2}>
            Booking Successful!
          </Heading>
          <Text color="green.700">
            Your booking has been created successfully. Redirecting you to the
            confirmation page...
          </Text>
        </Box>
      </VStack>
    )
  }

  return (
    <VStack gap={6} align="stretch">
      <Box>
        <Heading size="5xl" fontWeight="200" mb={2}>
          Review & Complete Booking
        </Heading>
        <Text mb={6}>
          Please review your booking details before completing payment.
        </Text>
      </Box>

      <Flex
        direction={{ base: "column", lg: "row" }}
        align="stretch"
        gap={6}
      >
        {/* Left Column - Booking Details */}
        <VStack gap={4} align="stretch" flex={1}>
          <Box>
            <Heading size="2xl" fontWeight="200" mb={4}>
              Booking Summary
            </Heading>
            <Separator mb={3} />
            <VStack gap={3} align="stretch">
              <HStack justify="space-between">
                <Text fontWeight="medium">Customer:</Text>
                <Text>
                  {bookingData.customerInfo.first_name}{" "}
                  {bookingData.customerInfo.last_name}
                </Text>
              </HStack>

              <HStack justify="space-between">
                <Text fontWeight="medium">Email:</Text>
                <Text>{bookingData.customerInfo.email}</Text>
              </HStack>

              <HStack justify="space-between">
                <Text fontWeight="medium">Phone:</Text>
                <Text>{bookingData.customerInfo.phone}</Text>
              </HStack>

              <HStack justify="space-between">
                <Text fontWeight="medium">Billing Address:</Text>
                <Text>{bookingData.customerInfo.billing_address}</Text>
              </HStack>
            </VStack>
          </Box>

          <Separator />

          <Box>
            <HStack justify="space-between">
              <Heading size="2xl" fontWeight="200" mb={4}>
                Selected Items
              </Heading>
              <Text mb={4} fontSize="2xl" color="whiteAlpha.500">
                {bookingData.selectedItems.length} selected
              </Text>
            </HStack>
            <VStack gap={3} align="stretch">
              {bookingData.selectedItems.map((item, index) => (
                <HStack
                  key={index}
                  justify="space-between"
                  p={3}
                  bg="bg.accent"
                  borderRadius="md"
                >
                  <Box>
                    <Text fontWeight="medium">
                      {item.item_type
                        .replace("_", " ")
                        .replace(/\b\w/g, (l) => l.toUpperCase())}
                      {item.variant_option
                        ? ` – ${item.variant_option}`
                        : ""}
                    </Text>
                    <Text fontSize="sm" color="gray.400">
                      Quantity: {item.quantity}
                    </Text>
                  </Box>
                  <Text fontWeight="semibold">
                    ${formatCents(item.price_per_unit * item.quantity)}
                  </Text>
                </HStack>
              ))}
            </VStack>
          </Box>
        </VStack>

        {/* Right Column - Payment */}
        <VStack gap={4} align="stretch">
          <Box>
            <Heading size="2xl" fontWeight="200" mb={4}>
              Payment Summary
            </Heading>
            <Separator mb={3} />
            <VStack gap={3} align="stretch">
              <HStack justify="space-between">
                <Text>Subtotal:</Text>
                <Text>${formatCents(bookingData.subtotal)}</Text>
              </HStack>

              {bookingData.discount_amount > 0 && (
                <HStack justify="space-between">
                  <Text>Discount:</Text>
                  <Text color="green.500">
                    -${formatCents(bookingData.discount_amount)}
                  </Text>
                </HStack>
              )}

              <HStack justify="space-between">
                <Text>Tax ({Number(bookingData.tax_rate.toFixed(2))}%):</Text>
                <Text>${formatCents(bookingData.tax_amount)}</Text>
              </HStack>

              {bookingData.tip > 0 && (
                <HStack justify="space-between">
                  <StarFleetTipLabel showColon />
                  <Text>${formatCents(bookingData.tip)}</Text>
                </HStack>
              )}

              <Separator />

              <HStack justify="space-between">
                <Text fontWeight="bold" fontSize="2xl">
                  Total:
                </Text>
                <Text fontWeight="bold" fontSize="2xl">
                  ${formatCents(bookingData.total)}
                </Text>
              </HStack>
            </VStack>
          </Box>

          <Box p={4} bg="bg.accent" borderRadius="md">
            <Text fontSize="xs" width="100%">
              Your payment will be processed securely. You'll receive a
              confirmation email with your QR code tickets once payment is
              complete.
            </Text>
          </Box>

          <Box>
            {bookingWithPayment && (
              <VStack gap={4} align="stretch">
                <StripeProvider
                  options={{
                    clientSecret: bookingWithPayment.paymentData.client_secret,
                  }}
                >
                  <PaymentForm
                    clientSecret={bookingWithPayment.paymentData.client_secret}
                    paymentIntentId={
                      bookingWithPayment.paymentData.payment_intent_id
                    }
                    amount={bookingData.total}
                    onPaymentSuccess={handlePaymentSuccess}
                    onPaymentError={handlePaymentError}
                    loading={completeBookingMutation.isPending}
                  />
                </StripeProvider>
              </VStack>
            )}
          </Box>
        </VStack>
      </Flex>

      {/* Navigation */}
      <Flex justify="flex-start" pt={4}>
        <Button variant="outline" onClick={onBack} size={{ base: "lg", sm: "md" }}>
          Back
        </Button>
      </Flex>
    </VStack>
  )
}

export default Step4Review
