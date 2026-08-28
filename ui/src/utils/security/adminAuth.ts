/**
 * Admin auth utilities for the frontend.
 *
 * The backend stores an scrypt hash of a client-side derived value. To avoid
 * sending the raw admin password over the wire, we derive a stable hash in the
 * browser and send that as `passwordHash` to the API. The server then verifies
 * that value against its stored scrypt hash.
 *
 * This uses the pure-JS `js-sha256` rather than the native
 * `crypto.subtle.digest`: SubtleCrypto is only exposed by browsers in a
 * "secure context" (HTTPS, or the special-cased http://localhost), so on a
 * plain-HTTP LAN address WireLoft is commonly reached at (e.g.
 * http://192.168.1.50:8080) `crypto.subtle` is `undefined` and calling it
 * throws -- which login's generic error handling then surfaces as a
 * misleading "Network error, please try again." js-sha256 produces a
 * byte-identical SHA-256 digest (verified against crypto.subtle output) but
 * works in any context.
 */
import { sha256 } from "js-sha256"

/** Convert an ArrayBuffer/TypedArray to a base64url string (no padding). */
function toBase64Url(bytes: ArrayBuffer | Uint8Array): string {
  const buffer = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  let binary = ""
  for (let i = 0; i < buffer.byteLength; i++) binary += String.fromCharCode(buffer[i])
  // btoa expects binary string; then convert to URL-safe and strip padding
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "")
}

/**
 * Deterministically hash the admin password in the browser using SHA-256 and
 * return a base64url string. This value is what we send to the backend as
 * `passwordHash`.
 */
export async function hashPasswordForAdminAuth(password: string): Promise<string> {
  const enc = new TextEncoder()
  const data = enc.encode(password)
  const digest = sha256.arrayBuffer(data)
  return toBase64Url(digest)
}
