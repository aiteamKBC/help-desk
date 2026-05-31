export function getCsrfToken() {
  if (typeof document === "undefined") {
    return "";
  }

  const csrfCookie = document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith("csrftoken="));

  if (!csrfCookie) {
    return "";
  }

  return decodeURIComponent(csrfCookie.slice("csrftoken=".length));
}

export function buildCsrfHeaders(headers: HeadersInit = {}) {
  const csrfToken = getCsrfToken();
  if (!csrfToken) {
    return headers;
  }

  return {
    ...headers,
    "X-CSRFToken": csrfToken,
  };
}
