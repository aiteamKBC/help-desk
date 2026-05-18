import type { BookingSummary } from "@/context/SupportContext";

export interface ApiBookingSummary {
  requestedDate?: string;
  requestedTime?: string;
  reservationConfirmed?: boolean;
  meetingJoinUrl?: string | null;
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

export function toBookingSummary(summary: ApiBookingSummary | null | undefined): BookingSummary | null {
  if (!summary?.requestedDate || !summary?.requestedTime) {
    return null;
  }

  const labels = formatBookingSummaryLabels(summary.requestedDate, summary.requestedTime);

  return {
    ...labels,
    reservationConfirmed: Boolean(summary.reservationConfirmed),
    meetingJoinUrl: summary.meetingJoinUrl || null,
  };
}
