import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, CalendarClock, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SupportLayout } from "@/components/support/SupportLayout";
import { StepIndicator } from "@/components/support/StepIndicator";
import { type ChatMessage } from "@/context/SupportContext";
import { useSupport } from "@/context/useSupport";
import {
  awaitingMeetingReason,
  canReturnToChat,
  getSupportResumePath,
  shouldShowStatusStep,
  type SupportBookingLocationState,
} from "@/lib/supportFlow";
import { setTicketBookingProgress } from "@/lib/supportTicketProgress";
import {
  fetchSupportSessionAvailability,
  type SupportSessionTimeOption,
} from "@/lib/supportBooking";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const ukSupportTimeZone = "Europe/London";
const ukSupportSessionStartMinutes = 8 * 60;
const ukSupportSessionEndMinutes = 16 * 60;
const supportSessionSlotIntervalMinutes = 30;
const supportSessionLeadTimeMs = 24 * 60 * 60 * 1000;

function buildTimestamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function buildBotMessage(text: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    sender: "bot",
    text,
    timestamp: buildTimestamp(),
  };
}

function formatDateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseLocalDateTime(dateValue: string, timeValue: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateValue) || !/^\d{2}:\d{2}$/.test(timeValue)) {
    return null;
  }

  const [year, month, day] = dateValue.split("-").map(Number);
  const [hours, minutes] = timeValue.split(":").map(Number);
  const parsed = new Date(year, month - 1, day, hours, minutes, 0, 0);

  if (
    Number.isNaN(parsed.getTime())
    || parsed.getFullYear() !== year
    || parsed.getMonth() !== month - 1
    || parsed.getDate() !== day
    || parsed.getHours() !== hours
    || parsed.getMinutes() !== minutes
  ) {
    return null;
  }

  return parsed;
}

function getTimeInTimeZoneMinutes(date: Date, timeZone: string) {
  const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = formatter.formatToParts(date);
  const hours = Number(parts.find((part) => part.type === "hour")?.value ?? Number.NaN);
  const minutes = Number(parts.find((part) => part.type === "minute")?.value ?? Number.NaN);

  if (Number.isNaN(hours) || Number.isNaN(minutes)) {
    return Number.NaN;
  }

  return (hours * 60) + minutes;
}

function isMinutesWithinRange(minutes: number, startMinutes: number, endMinutes: number) {
  return minutes >= startMinutes && minutes <= endMinutes;
}

function isWithinSupportSessionWindow(requestedDateTime: Date) {
  const ukMinutes = getTimeInTimeZoneMinutes(requestedDateTime, ukSupportTimeZone);
  return isMinutesWithinRange(ukMinutes, ukSupportSessionStartMinutes, ukSupportSessionEndMinutes);
}

function isSupportSessionTimeAligned(requestedDateTime: Date) {
  const localMinutes = (requestedDateTime.getHours() * 60) + requestedDateTime.getMinutes();
  return localMinutes % supportSessionSlotIntervalMinutes === 0;
}

function getSupportSessionValidationMessage(dateValue: string, timeValue: string, now = new Date()) {
  if (!dateValue || !timeValue) {
    return "";
  }

  const requestedDateTime = parseLocalDateTime(dateValue, timeValue);
  if (!requestedDateTime) {
    return "Please choose a valid session date and time.";
  }

  if ((requestedDateTime.getTime() - now.getTime()) <= supportSessionLeadTimeMs) {
    return "Support sessions must be booked more than 24 hours in advance.";
  }

  if (!isSupportSessionTimeAligned(requestedDateTime)) {
    return "Support sessions must start on 30-minute intervals.";
  }

  if (!isWithinSupportSessionWindow(requestedDateTime)) {
    return "Support sessions must be between 8:00 AM and 4:00 PM UK time.";
  }

  return "";
}

function buildSupportSessionTimeOptions(dateValue: string, now = new Date()) {
  if (!dateValue) {
    return [];
  }

  const options: Array<{ value: string; label: string }> = [];

  for (let minutes = 0; minutes < 24 * 60; minutes += supportSessionSlotIntervalMinutes) {
    const hours = String(Math.floor(minutes / 60)).padStart(2, "0");
    const mins = String(minutes % 60).padStart(2, "0");
    const value = `${hours}:${mins}`;
    const requestedDateTime = parseLocalDateTime(dateValue, value);

    if (!requestedDateTime) {
      continue;
    }

    if ((requestedDateTime.getTime() - now.getTime()) <= supportSessionLeadTimeMs) {
      continue;
    }

    if (!isWithinSupportSessionWindow(requestedDateTime)) {
      continue;
    }

    options.push({
      value,
      label: new Intl.DateTimeFormat("en-US", {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      }).format(requestedDateTime),
    });
  }

  return options;
}

function formatSupportSessionDetails(dateValue: string, timeValue: string) {
  const requestedDateTime = parseLocalDateTime(dateValue, timeValue);

  if (!requestedDateTime) {
    return {
      dateLabel: dateValue,
      timeLabel: timeValue,
    };
  }

  return {
    dateLabel: new Intl.DateTimeFormat("en-US", {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
    }).format(requestedDateTime),
    timeLabel: new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }).format(requestedDateTime),
  };
}

const EmbeddedBooking = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { ticket, bookingSummary, updateTicket, setBookingSummary } = useSupport();
  const [bookingDate, setBookingDate] = useState("");
  const [bookingTime, setBookingTime] = useState("");
  const [bookingTimeOptions, setBookingTimeOptions] = useState<SupportSessionTimeOption[]>([]);
  const [isLoadingAvailability, setIsLoadingAvailability] = useState(false);
  const [isBooking, setIsBooking] = useState(false);
  const requestedReturnPath = (location.state as SupportBookingLocationState | null)?.returnPath;
  const returnPath = requestedReturnPath || (canReturnToChat(ticket) ? "/support/chat" : "/support/options");
  const hasStatusStep = shouldShowStatusStep(ticket, bookingSummary);

  useEffect(() => {
    if (!ticket.id) {
      navigate(ticket.email ? "/support/options" : "/support");
      return;
    }

    if (!ticket.email) {
      navigate("/support");
      return;
    }

    if (hasStatusStep) {
      navigate(getSupportResumePath(ticket, bookingSummary));
    }
  }, [bookingSummary, hasStatusStep, navigate, ticket]);

  const minBookingDate = formatDateInputValue(new Date());
  const bookingValidationMessage = getSupportSessionValidationMessage(bookingDate, bookingTime);

  useEffect(() => {
    if (!bookingDate || !ticket.id) {
      setBookingTimeOptions([]);
      setIsLoadingAvailability(false);
      return;
    }

    let cancelled = false;
    setIsLoadingAvailability(true);
    setBookingTimeOptions([]);

    const loadAvailability = async () => {
      try {
        const payload = await fetchSupportSessionAvailability(
          ticket.id,
          bookingDate,
          Intl.DateTimeFormat().resolvedOptions().timeZone || "",
        );

        if (cancelled) {
          return;
        }

        setBookingTimeOptions(payload.options || []);
      } catch {
        if (!cancelled) {
          setBookingTimeOptions(buildSupportSessionTimeOptions(bookingDate));
        }
      } finally {
        if (!cancelled) {
          setIsLoadingAvailability(false);
        }
      }
    };

    void loadAvailability();

    return () => {
      cancelled = true;
    };
  }, [bookingDate, ticket.id]);

  useEffect(() => {
    if (!ticket.id || hasStatusStep) {
      return;
    }

    void setTicketBookingProgress(ticket.id, true);
  }, [hasStatusStep, ticket.id]);

  const handleBack = async () => {
    if (ticket.id) {
      await setTicketBookingProgress(ticket.id, false);
    }

    navigate(returnPath);
  };

  const handleBooking = async () => {
    if (!ticket.id || !bookingDate || !bookingTime) {
      return;
    }

    const requestedDateTime = parseLocalDateTime(bookingDate, bookingTime);

    if (bookingValidationMessage) {
      toast.error(bookingValidationMessage);
      return;
    }

    if (!requestedDateTime) {
      toast.error("Please choose a valid session date and time.");
      return;
    }

    setIsBooking(true);

    try {
      const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.id)}/session-requests`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          date: bookingDate,
          time: bookingTime,
          scheduledAt: requestedDateTime.toISOString(),
          clientTimeZone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
          returnPath,
        }),
      });

      const payload = (await response.json().catch(() => null)) as {
        message?: string;
        webhookConfigured?: boolean;
        webhookDelivered?: boolean;
        reservationConfirmed?: boolean;
        meetingJoinUrl?: string | null;
        ticket?: {
          status?: string;
          statusReason?: string;
          assignedTeam?: string;
        };
      } | null;

      if (!response.ok) {
        toast.error(payload?.message || "We could not save the support session request.");
        return;
      }

      const bookingDetails = formatSupportSessionDetails(bookingDate, bookingTime);
      const bookingConfirmationMessage = payload?.reservationConfirmed
        ? `Your support session has been booked for ${bookingDetails.dateLabel} at ${bookingDetails.timeLabel}. The Teams slot is now reserved for you.`
        : `Thank you. Your support session request has been submitted for ${bookingDetails.dateLabel} at ${bookingDetails.timeLabel}. Our team will review it and confirm the next steps with you shortly.`;

      updateTicket({
        status: (payload?.ticket?.status as typeof ticket.status | undefined) || "Pending",
        statusReason: payload?.ticket?.statusReason || awaitingMeetingReason,
        assignedTeam: payload?.ticket?.assignedTeam || ticket.assignedTeam,
        chatHistory: [...ticket.chatHistory, buildBotMessage(bookingConfirmationMessage)],
      });
      setBookingSummary({
        ...bookingDetails,
        reservationConfirmed: Boolean(payload?.reservationConfirmed),
        meetingJoinUrl: payload?.meetingJoinUrl || null,
        returnPath,
      });
      setBookingDate("");
      setBookingTime("");

      if (payload?.reservationConfirmed) {
        toast.success("Your Teams support session has been reserved successfully.");
      } else if (payload?.webhookConfigured === false) {
        toast.success("Your request has been submitted successfully. Our team will review it shortly.");
      } else if (payload?.webhookDelivered === false) {
        toast.success("Your request has been submitted successfully. Confirmation may take a little longer than usual.");
      } else {
        toast.success("Your support session request has been submitted successfully.");
      }

      navigate("/support/status");
    } catch {
      toast.error("We could not connect to the server. Please try again.");
    } finally {
      setIsBooking(false);
    }
  };

  return (
    <SupportLayout>
      <StepIndicator current={3} />
      <div className="mx-auto max-w-6xl">
        <div className="rounded-[28px] border border-primary/10 bg-gradient-to-br from-white via-white to-primary/[0.04] p-6 shadow-card md:p-8">
          <div className="flex items-start justify-between gap-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/[0.06] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/80">
              <span className="h-1.5 w-1.5 rounded-full bg-primary/75" />
              Booking Session
            </div>
            <Button variant="ghost" onClick={() => void handleBack()} className="shrink-0">
              <ArrowLeft className="mr-2 h-4 w-4" />
              {returnPath === "/support/chat" ? "Back to Chat" : "Back"}
            </Button>
          </div>

          <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
            <section className="rounded-[26px] border border-primary/12 bg-card/90 p-5 shadow-soft md:p-6">
              <div className="flex items-start gap-3">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-soft">
                  <CalendarClock className="h-5 w-5" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-primary">Book a Support Session</h1>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                    Choose a date and time that works for you on a dedicated booking page, without showing the chat in the background.
                  </p>
                </div>
              </div>

              <div className="mt-6 space-y-5">
                <div className="rounded-2xl border border-primary/15 bg-primary/[0.04] p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-primary">Aptem Email</div>
                  <div className="mt-2 text-lg font-semibold text-foreground break-all">{ticket.email}</div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    This is the email address that will be used for your booking and follow-up.
                  </p>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="booking-date">Date</Label>
                    <Input
                      id="booking-date"
                      type="date"
                      min={minBookingDate}
                      value={bookingDate}
                      onChange={(event) => {
                        setBookingDate(event.target.value);
                        setBookingTime("");
                      }}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="booking-time">Time</Label>
                    <Select
                      value={bookingTime}
                      onValueChange={setBookingTime}
                      disabled={!bookingDate || isLoadingAvailability || bookingTimeOptions.length === 0}
                    >
                      <SelectTrigger id="booking-time">
                        <SelectValue placeholder={bookingDate ? (isLoadingAvailability ? "Loading available times..." : "Select a time slot") : "Choose a date first"} />
                      </SelectTrigger>
                      <SelectContent>
                        {bookingTimeOptions.map((option) => (
                          <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {bookingDate && !isLoadingAvailability && bookingTimeOptions.length === 0 ? (
                  <p className="text-xs text-destructive">
                    No available session times match the 24-hour notice and UK support hours for this date.
                  </p>
                ) : null}

                <p className={cn("text-xs", bookingValidationMessage ? "text-destructive" : "text-muted-foreground")}>
                  {bookingValidationMessage || "Allowed meeting hours are 8:00 AM to 4:00 PM UK time, with more than 24 hours notice required, and sessions start on 30-minute intervals."}
                </p>

                <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
                  <Button variant="outline" onClick={() => navigate(returnPath)}>
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    {returnPath === "/support/chat" ? "Return to Chat" : "Back"}
                  </Button>
                  <Button
                    className="border-0 gradient-primary"
                    disabled={!bookingDate || !bookingTime || Boolean(bookingValidationMessage) || isBooking}
                    onClick={() => void handleBooking()}
                  >
                    <Check className="mr-2 h-4 w-4" />
                    {isBooking ? "Saving..." : "Confirm Booking"}
                  </Button>
                </div>
              </div>
            </section>

            <aside className="rounded-[26px] border border-primary/12 bg-card/90 p-5 shadow-soft md:p-6">
              <div className="text-sm font-semibold uppercase tracking-wide text-primary/80">Summary</div>
              <div className="mt-5 space-y-4 text-sm">
                <div>
                  <div className="text-muted-foreground">Ticket</div>
                  <div className="mt-1 font-medium text-foreground">{ticket.id || "-"}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Learner</div>
                  <div className="mt-1 font-medium text-foreground">{ticket.learnerName || ticket.email || "-"}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Category</div>
                  <div className="mt-1 font-medium text-foreground">
                    {ticket.category}{ticket.technicalSubcategory ? ` - ${ticket.technicalSubcategory}` : ""}
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground">Inquiry</div>
                  <div className="mt-1 whitespace-pre-wrap font-medium text-foreground">{ticket.inquiry || "-"}</div>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </div>
    </SupportLayout>
  );
};

export default EmbeddedBooking;
