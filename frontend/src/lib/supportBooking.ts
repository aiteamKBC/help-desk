import type { BookingSummary } from "@/context/SupportContext";

export interface ApiBookingSummary {
  requestedDate?: string;
  requestedTime?: string;
  reservationConfirmed?: boolean;
  meetingJoinUrl?: string | null;
  returnPath?: string | null;
}

export interface SupportSessionTimeOption {
  value: string;
  label: string;
}

export interface SupportSessionAvailabilityResponse {
  ok?: boolean;
  date?: string;
  source?: "microsoft_graph" | "fallback";
  options?: SupportSessionTimeOption[];
  message?: string;
}

export async function fetchSupportSessionAvailability(
  ticketId: string,
  dateValue: string,
  clientTimeZone: string,
) {
  const params = new URLSearchParams({
    date: dateValue,
    clientTimeZone,
  });
  const response = await fetch(`/api/tickets/${encodeURIComponent(ticketId)}/session-availability?${params.toString()}`);
  const payload = (await response.json().catch(() => null)) as SupportSessionAvailabilityResponse | null;

  if (!response.ok || !payload) {
    throw new Error(payload?.message || "We could not load support session availability.");
  }

  return {
    ...payload,
    options: Array.isArray(payload.options) ? payload.options : [],
  };
}

function parseLocalDateTime(dateValue: string, timeValue: string) {
  const [year, month, day] = dateValue.split("-").map(Number);
  const [hours, minutes] = timeValue.split(":").map(Number);

  if (
    !Number.isInteger(year)
    || !Number.isInteger(month)
    || !Number.isInteger(day)
    || !Number.isInteger(hours)
    || !Number.isInteger(minutes)
  ) {
    return null;
  }

  return new Date(year, month - 1, day, hours, minutes);
}

export function formatBookingSummaryLabels(dateValue: string, timeValue: string) {
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

function normalizeBookingReturnPath(value: unknown): BookingSummary["returnPath"] {
  return value === "/support/chat" || value === "/support/options" ? value : undefined;
}

export function toBookingSummary(summary: ApiBookingSummary | null | undefined): BookingSummary | null {
  if (!summary?.requestedDate || !summary?.requestedTime) {
    return null;
  }

  const labels = formatBookingSummaryLabels(summary.requestedDate, summary.requestedTime);
  const returnPath = normalizeBookingReturnPath(summary.returnPath);

  const bookingSummary: BookingSummary = {
    ...labels,
    reservationConfirmed: Boolean(summary.reservationConfirmed),
    meetingJoinUrl: summary.meetingJoinUrl || null,
  };
  if (returnPath) {
    bookingSummary.returnPath = returnPath;
  }

  return bookingSummary;
}
