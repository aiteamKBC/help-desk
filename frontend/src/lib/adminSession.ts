export interface AdminSession {
  id: number;
  username: string;
  fullName: string;
  email: string | null;
  role: string;
}

const storageKey = "support_admin_session";

export function getAdminSession(): AdminSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawValue = sessionStorage.getItem(storageKey);
  if (!rawValue) {
    return null;
  }

  try {
    return JSON.parse(rawValue) as AdminSession;
  } catch {
    sessionStorage.removeItem(storageKey);
    return null;
  }
}

export function setAdminSession(session: AdminSession) {
  sessionStorage.setItem(storageKey, JSON.stringify(session));
}

export function clearAdminSession() {
  sessionStorage.removeItem(storageKey);
}
