# LMS → Support Portal SSO — Integration Handoff

**For:** the developer implementing the LMS side.
**Status of the support portal (help-desk) side:** complete and deployed on branch
`feat/native-assistant-lms-integration`. Nothing below requires a change to the support portal.

---

## 1. What this integration does

A signed-in LMS learner clicks a "Technical Support" button. The LMS mints a short-lived
signed token for that learner and redirects the browser to the support portal, which opens
a chatbot already knowing who the learner is — no second login, no typing their email.

```
Learner clicks button in LMS
  └─> GET /login_api/support/authorize/      (browser carries the LMS session cookie)
        └─> LMS verifies the session, mints a signed token, 302 redirect
              └─> https://technicalsupport.kentbusinesscollege.net/lms?token=<token>
                    └─> Support portal verifies the token, resolves the learner,
                        opens the assistant. Tickets are created lazily.
```

The email is never passed in a plain query string — a `?email=` link would be trivially
spoofable. The HMAC signature is what makes the portal trust the identity.

---

## 2. Already done on the support portal side

| Piece | Location | Status |
| --- | --- | --- |
| `/lms` entry page (chat opens directly, no wizard) | `frontend/src/pages/support/LmsChat.tsx` | Done |
| Route registration | `frontend/src/App.tsx` → `<Route path="/lms" …>` | Done |
| Token verification | `backend/support_portal/services.py` → `verify_support_sso_token()` | Done |
| Assistant endpoint | `POST /api/support/assistant` (accepts `token`) | Done |
| Config key | `SUPPORT_SSO_SECRET` in `backend/.env` | Done |

The page accepts the learner, answers from the knowledge base, and offers three actions —
**Live Agent**, **Book Session**, **Submit Ticket** — creating a ticket only when one is
actually needed.

---

## 3. What the LMS side must implement

### 3.1 An authorize endpoint

Because LiteSpeed forwards only `*_api`-prefixed paths to Django, the endpoint must live
under `login_api/`. Suggested route:

```python
# login/urls.py
path("support/authorize/", support_sso.authorize, name="support-authorize"),
```

The endpoint must:

1. Resolve the current LMS session (`authenticate_request(request)`), returning **401** if
   there is no active, enabled account. Identity comes from the session — **never** from a
   query parameter.
2. Mint a token (format in §4) for `account.email`.
3. Redirect to `SUPPORT_SSO_CALLBACK_URL + "?token=" + token`.
4. Send `Cache-Control: no-store` and `Referrer-Policy: no-referrer` so the token is not
   cached or leaked in a referrer header.

A working reference implementation is provided — see §6.

### 3.2 A button in the LMS UI

This is a plain link; no JavaScript, no `state` round-trip. It is **much simpler** than the
existing `SafeguardingSignIn` / `InclusionSignIn` components, because here the LMS is the
origin rather than the responder:

```html
<a href="/login_api/support/authorize/" target="_blank" rel="noopener noreferrer">
  Technical Support
</a>
```

Natural placement: `frontend/src/components/feature/Header.tsx`, alongside the other
learner navigation links.

### 3.3 Settings

```env
SUPPORT_SSO_SECRET=<shared secret — see §5>
SUPPORT_SSO_CALLBACK_URL=https://technicalsupport.kentbusinesscollege.net/lms
SUPPORT_SSO_TOKEN_TTL=300
```

---

## 4. Token contract (must match exactly)

The portal rejects anything that deviates from this. Verified against
`verify_support_sso_token()` in `backend/support_portal/services.py`.

**Shape**

```
base64url(payload_json) "." base64url(hmac_sha256_signature)
```

Exactly one `.` — a token with zero or two or more dots is rejected outright.

**Payload**

```json
{"email": "learner@example.com", "iat": 1760000000, "exp": 1760000300}
```

| Field | Required | Rule |
| --- | --- | --- |
| `email` | yes | Must be a valid address and resolve to a learner in the support database |
| `exp` | yes | Unix seconds. Rejected once `now > exp`. Must be a number, not a boolean |
| `iat` | recommended | Unix seconds. If present, `exp - iat` must be **≤ 305** (`SUPPORT_SSO_TOKEN_MAX_AGE_SECONDS` is 300, plus 5s slack) |

A long-lived token is refused even before it expires — that is the point of the `iat` check,
so keep the TTL at 300 seconds.

**Signature**

`HMAC-SHA256(secret, base64url(payload_json))` — note carefully: the signature covers the
**base64url-encoded payload string**, not the raw JSON bytes.

**Padding**

Base64url `=` padding may be stripped; the portal re-adds it before decoding. Stripping is
what the reference implementation does.

> ⚠️ Do **not** use `django.core.signing` here. The LMS's existing `safeguarding_sso.py`
> uses `signing.dumps()`, which produces a different format that this endpoint will reject.
> The two mechanisms are deliberately separate so their secrets never cross purposes.

---

## 5. The shared secret

`SUPPORT_SSO_SECRET` must be **byte-identical** on both sides — it is the only thing making
the signature verifiable. It is not included in this document on purpose.

Obtain it from the help-desk `backend/.env` (ask Khaled), transfer it over a secure channel,
and store it only in the LMS server's `.env`. If the two values differ, every token fails
with `401 "This sign-in link could not be verified."`

---

## 6. Reference implementation

A complete, working `support_sso.py` has already been written and is available at:

```
backend/login/support_sso.py
```

in the LMS working copy at `E:\Projects\lms_updates\LMS_v2` (currently uncommitted on
`main`, alongside the one-line addition to `login/urls.py`). It produces exactly the format
in §4. Use it as-is or as a starting point.

Core of it, for reference:

```python
def _issue_token(email: str, secret: str, ttl: int = 300) -> str:
    now = int(time.time())
    payload = {"email": email, "iat": now, "exp": now + ttl}
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url(sig)}"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
```

---

## 7. Verifying the integration

1. Sign in to the LMS as a learner whose email also exists in the support database.
2. Click the support button. The browser should land on
   `…/lms?token=…` with the assistant greeting the learner by name.
3. Ask the assistant something it cannot resolve, or press **Submit Ticket** — a ticket
   should appear in the support dashboard against that learner.

**Troubleshooting**

| Symptom | Cause |
| --- | --- |
| `401 This sign-in link could not be verified` | Secrets differ between the two `.env` files |
| `401 This sign-in link is invalid` | Wrong token shape, or `exp - iat` exceeds 305s |
| `401 This sign-in link has expired` | Clock skew between servers, or the learner sat on the redirect |
| `503 Single sign-on is not configured` | `SUPPORT_SSO_SECRET` missing on the portal |
| Assistant answers but cannot open a ticket | The email is not a known learner in the support database |

Tokens last five minutes, which covers the redirect. The `/lms` page does not keep reusing
the token afterwards, so a long chat session will not expire mid-conversation.

---

## 8. Checklist

- [ ] `support_sso.py` added under `login/`
- [ ] `path("support/authorize/", …)` registered in `login/urls.py`
- [ ] Support button added to the LMS UI
- [ ] Three settings added to the LMS server `.env`
- [ ] `SUPPORT_SSO_SECRET` confirmed identical on both servers
- [ ] LiteSpeed confirmed to forward `login_api/support/authorize/` to Django
- [ ] Django restarted, frontend rebuilt
- [ ] End-to-end test from §7 passes

---

## 9. Contact

Support portal side (`/lms` page, token verification, assistant, tickets): **Khaled Ashraf**
— `engagement@kentbusinesscollege.com`. The portal needs no further changes for this
integration; if a token is being rejected, compare it against §4 first.
