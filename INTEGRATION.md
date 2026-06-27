# Cloud drive ⇄ space-io editor integration

This drive (the **host**) can be paired with the [space-io editor](https://github.com/nasko05/space-io)
(the **plug-in**) so one email-less passkey signs you into both and you can hop
between them. **The pairing is entirely opt-in config — with none of it set, the
drive runs exactly as it always has, and never references the editor.**

## The contract

The two apps share only:

1. **A secret.** The drive signs its session JWT with `DRIVE_SECRET_KEY` (HS256).
   The editor verifies that token with the *same* value (`SPACEIO_SSO_JWT_SECRET`).
2. **A cookie.** On every login (password *and* passkey) the drive mirrors the
   JWT into a cookie scoped to the registrable parent domain, so a sibling app on
   `personal-area.<domain>` is signed in too. `POST /v2/auth/logout` clears it.
3. **One passkey, two subdomains.** Passkeys are registered with the **PRF
   (`hmac-secret`) extension** and an RP ID equal to the parent domain, so the
   editor can (a) reuse the credential from its subdomain and (b) derive its
   note-encryption key from the PRF output. The drive itself never evaluates PRF.
4. **Two URLs.** Each app links to the other.

No shared database, no shared build, no shared deploy. Two repos, two images, two
pipelines.

## Environment knobs (drive side)

All optional; unset = standalone drive.

| Variable | Purpose |
|---|---|
| `DRIVE_SECRET_KEY` | HS256 secret for the JWT. The editor must use the same value. |
| `DRIVE_SSO_COOKIE_DOMAIN` | Set to the registrable parent, e.g. `.example.com`, to share the session across subdomains. Empty = host-only cookie (standalone). |
| `DRIVE_SSO_COOKIE_NAME` | Cookie name (default `drive_sso`); must match the editor's `SPACEIO_SSO_COOKIE_NAME`. |
| `DRIVE_SSO_COOKIE_SECURE` / `DRIVE_SSO_COOKIE_SAMESITE` | `true` / `lax` by default. Use `false` only for plain-HTTP local dev. |
| `DRIVE_WEBAUTHN_RP_ID` | The **parent** domain (e.g. `example.com`) so the passkey works on both apps. Must match the editor's `VITE_WEBAUTHN_RP_ID`. |
| `DRIVE_WEBAUTHN_ORIGIN` | Comma-separated allowed origins (both the drive and editor URLs). |
| `VITE_PERSONAL_AREA_URL` *(frontend build)* | Full URL of the editor; when set, a **"My Space"** link appears in the top bar. |

## Deployment

The drive's `Caddyfile` already reverse-proxies `personal-area.<domain>` to the
space-io container over the shared external `web` network. Bring up each app's
own `docker compose` stack; they meet only at Caddy and at the shared secret.

## What's NOT shared

- The drive stores files unencrypted (as always); the editor encrypts its notes
  end-to-end. They never read each other's storage.
- The in-app file previews (PDF/DOCX/image/video) are the drive's **own** code,
  copied from the editor — no runtime dependency on it.

## Re-enrollment note

PRF must be present when a passkey is *created*. Passkeys registered before this
integration won't have it, so to unlock the editor a user must **register a new
passkey once**. Drive login keeps working with any passkey.

See the editor's `INTEGRATION.md` for the other side, and the bottom of that file
for a full end-to-end manual test checklist.
