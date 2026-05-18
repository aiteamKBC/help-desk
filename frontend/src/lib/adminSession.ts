export interface AdminSession {
  id: number;
  username: string;
  fullName: string;
  email: string | null;
  role: string;
  instanceId: string;
  consoleStatus?: string;
}

const storageKey = "support_admin_session";

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

export function clearAdminSession() {
  sessionStorage.removeItem(storageKey);
}
