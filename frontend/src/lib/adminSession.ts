export interface AdminSession {
  id: number;
  username: string;
  fullName: string;
  email: string | null;
  role: string;
  instanceId: string;
  sessionActive?: boolean;
  consoleStatus?: string;
  selectedConsoleStatus?: string;
  legacySupportAccess?: boolean;
  legacyOperationsAccess?: boolean;
  legacyAdminAccess?: boolean;
  entraDirectoryAdmin?: boolean;
  teamAccess?: Array<{
    key: string;
    name?: string;
    assignedTeam?: string;
    label?: string;
    canReceiveTickets?: boolean;
  }>;
  teamAccessKeys?: string[];
}

interface AdminSessionResponse {
  admin?: AdminSession;
  message?: string;
}

const storageKey = "support_admin_session";
const adminPortalReturnStorageKey = "support_admin_portal_return";
export const adminPortalReturnQueryParam = "adminPortalReturn";

export function createAdminSessionInstanceId() {
  if (typeof window !== "undefined" && typeof window.crypto?.randomUUID === "function") {
    return window.crypto.randomUUID();
  }

  return `support-session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function getAdminSession(): AdminSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawValue = sessionStorage.getItem(storageKey);
  if (!rawValue) {
    return null;
  }

  try {
    const parsedValue = JSON.parse(rawValue) as Partial<AdminSession>;
    const session = {
      ...parsedValue,
      instanceId: parsedValue.instanceId || createAdminSessionInstanceId(),
    } as AdminSession;

    sessionStorage.setItem(storageKey, JSON.stringify(session));
    return session;
  } catch {
    sessionStorage.removeItem(storageKey);
    return null;
  }
}

export function setAdminSession(session: AdminSession) {
  sessionStorage.setItem(storageKey, JSON.stringify(session));
}

export function setAdminSessionOnWindow(targetWindow: Window, session: AdminSession) {
  targetWindow.sessionStorage.setItem(storageKey, JSON.stringify(session));
}

export function markAdminPortalReturnEnabled() {
  if (typeof window === "undefined") {
    return;
  }

  sessionStorage.setItem(adminPortalReturnStorageKey, "1");
}

export function syncAdminPortalReturnFromSearch(search: string) {
  if (typeof window === "undefined") {
    return;
  }

  const searchParams = new URLSearchParams(search);
  if (searchParams.get(adminPortalReturnQueryParam) === "1") {
    markAdminPortalReturnEnabled();
  }
}

export function canReturnToAdminDashboard() {
  if (typeof window === "undefined") {
    return false;
  }

  return sessionStorage.getItem(adminPortalReturnStorageKey) === "1";
}

export function clearAdminPortalReturnFlag() {
  if (typeof window === "undefined") {
    return;
  }

  sessionStorage.removeItem(adminPortalReturnStorageKey);
}

export function clearAdminSession() {
  sessionStorage.removeItem(storageKey);
  clearAdminPortalReturnFlag();
}

export function isSameAdminSession(left: AdminSession | null | undefined, right: AdminSession | null | undefined) {
  if (!left || !right) {
    return false;
  }

  return left.id === right.id
    && left.instanceId === right.instanceId
    && left.username.trim().toLowerCase() === right.username.trim().toLowerCase();
}

export function isSameAdminIdentity(left: AdminSession | null | undefined, right: AdminSession | null | undefined) {
  if (!left || !right) {
    return false;
  }

  return left.id === right.id
    && left.username.trim().toLowerCase() === right.username.trim().toLowerCase();
}

export async function fetchVerifiedAdminSession(signal?: AbortSignal) {
  const response = await fetch("/api/admin/session", {
    method: "GET",
    signal,
  });
  const payload = (await response.json().catch(() => null)) as AdminSessionResponse | null;

  return {
    response,
    payload,
    admin: payload?.admin || null,
  };
}
