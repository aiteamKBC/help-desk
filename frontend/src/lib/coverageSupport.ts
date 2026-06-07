export interface CoverageDetails {
  tutor: string;
  module: string;
  time: string;
  sessionDates?: string[];
  sessionNumbers?: string[];
  sessionSubjects?: string[];
  sessionSubject: string;
}

export type CoverageOptionType = "tutors" | "modules" | "times" | "session-dates";

export interface CoverageTimeOption {
  label: string;
  completed: boolean;
  endDate?: string;
}

const coverageInquiryLinePatterns = {
  tutor: /^Tutor:\s*(.+)$/im,
  module: /^Module:\s*(.+)$/im,
  time: /^Preferred Time:\s*(.+)$/im,
  sessionDates: /^Session Date:\s*(.+)$/im,
  sessionNumbers: /^Session Number:\s*(.+)$/im,
  sessionSubject: /^Session Subject:\s*(.+)$/im,
};

export const isCoverageSubcategory = (value: string) => value.trim().toLowerCase() === "coverage";

function normalizeCoverageTimeOption(value: unknown): CoverageTimeOption | null {
  if (typeof value === "string") {
    const label = value.trim();
    return label ? { label, completed: false } : null;
  }

  if (!value || typeof value !== "object") {
    return null;
  }

  const payload = value as { label?: unknown; completed?: unknown; endDate?: unknown };
  const label = typeof payload.label === "string" ? payload.label.trim() : "";
  if (!label) {
    return null;
  }

  return {
    label,
    completed: Boolean(payload.completed),
    endDate: typeof payload.endDate === "string" ? payload.endDate : "",
  };
}

export async function fetchCoverageOptions(
  type: CoverageOptionType,
  params?: {
    tutor?: string;
    module?: string;
    time?: string;
  },
) {
  const query = new URLSearchParams({ type });
  if (params?.tutor) {
    query.set("tutor", params.tutor);
  }
  if (params?.module) {
    query.set("module", params.module);
  }
  if (params?.time) {
    query.set("time", params.time);
  }

  const response = await fetch(`/api/coverage-options?${query.toString()}`, {
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => null)) as
    | {
        message?: string;
        options?: string[];
      }
    | null;

  if (!response.ok) {
    throw new Error(payload?.message || "We could not load the coverage options right now.");
  }

  return Array.isArray(payload?.options) ? payload.options.filter((item): item is string => typeof item === "string") : [];
}

export async function fetchCoverageTimeOptions(params: {
  tutor?: string;
  module?: string;
}) {
  const query = new URLSearchParams({ type: "times" });
  if (params.tutor) {
    query.set("tutor", params.tutor);
  }
  if (params.module) {
    query.set("module", params.module);
  }

  const response = await fetch(`/api/coverage-options?${query.toString()}`, {
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => null)) as
    | {
        message?: string;
        options?: string[];
        items?: unknown[];
      }
    | null;

  if (!response.ok) {
    throw new Error(payload?.message || "We could not load the coverage times right now.");
  }

  const rawItems = Array.isArray(payload?.items) && payload.items.length > 0
    ? payload.items
    : Array.isArray(payload?.options)
      ? payload.options
      : [];

  return rawItems
    .map((item) => normalizeCoverageTimeOption(item))
    .filter((item): item is CoverageTimeOption => Boolean(item));
}

export async function fetchCoverageTutorEmail(tutor: string) {
  const query = new URLSearchParams({
    type: "tutor-email",
    tutor,
  });

  const response = await fetch(`/api/coverage-options?${query.toString()}`, {
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => null)) as
    | {
        message?: string;
        value?: string;
      }
    | null;

  if (!response.ok) {
    throw new Error(payload?.message || "We could not load the tutor e-mail right now.");
  }

  return typeof payload?.value === "string" ? payload.value.trim() : "";
}

export function buildCoverageInquiry(details: CoverageDetails) {
  const sessionDates = Array.isArray(details.sessionDates)
    ? details.sessionDates.map((value) => value.trim()).filter(Boolean)
    : [];
  const sessionNumbers = Array.isArray(details.sessionNumbers)
    ? details.sessionNumbers.map((value) => value.trim()).filter(Boolean)
    : [];
  const sessionSubjects = Array.isArray(details.sessionSubjects)
    ? details.sessionSubjects.map((value) => value.trim()).filter(Boolean)
    : [];
  const normalizedSessionSubjects = sessionSubjects.length > 0
    ? sessionSubjects
    : details.sessionSubject.trim()
      ? [details.sessionSubject.trim()]
      : [];

  return [
    "Coverage session request",
    `Tutor: ${details.tutor.trim()}`,
    `Module: ${details.module.trim()}`,
    `Preferred Time: ${details.time.trim()}`,
    sessionDates.length > 0 ? `Session Date: ${sessionDates.join("; ")}` : "",
    sessionNumbers.length > 0 ? `Session Number: ${sessionNumbers.join("; ")}` : "",
    normalizedSessionSubjects.length > 0 ? `Session Subject: ${normalizedSessionSubjects.join("; ")}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

export function parseCoverageInquiry(inquiry: string): CoverageDetails | null {
  const normalizedInquiry = inquiry.trim();
  if (!normalizedInquiry) {
    return null;
  }

  const tutor = normalizedInquiry.match(coverageInquiryLinePatterns.tutor)?.[1]?.trim() || "";
  const module = normalizedInquiry.match(coverageInquiryLinePatterns.module)?.[1]?.trim() || "";
  const time = normalizedInquiry.match(coverageInquiryLinePatterns.time)?.[1]?.trim() || "";
  const sessionDates = (normalizedInquiry.match(coverageInquiryLinePatterns.sessionDates)?.[1] || "")
    .split(";")
    .map((value) => value.trim())
    .filter(Boolean);
  const sessionNumbers = (normalizedInquiry.match(coverageInquiryLinePatterns.sessionNumbers)?.[1] || "")
    .split(";")
    .map((value) => value.trim())
    .filter(Boolean);
  const sessionSubjects = (normalizedInquiry.match(coverageInquiryLinePatterns.sessionSubject)?.[1] || "")
    .split(";")
    .map((value) => value.trim())
    .filter(Boolean);
  const sessionSubject = sessionSubjects.length <= 1 ? (sessionSubjects[0] || "") : sessionSubjects.join("; ");

  if (!tutor && !module && !time && sessionDates.length === 0 && sessionNumbers.length === 0 && sessionSubjects.length === 0) {
    return null;
  }

  return {
    tutor,
    module,
    time,
    sessionDates,
    sessionNumbers,
    sessionSubjects,
    sessionSubject,
  };
}
