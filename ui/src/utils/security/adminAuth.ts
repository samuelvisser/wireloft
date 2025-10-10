/**
 * Admin auth utilities for the frontend.
 *
 * The backend stores an scrypt hash of a client-side derived value. To avoid
 * sending the raw admin password over the wire, we derive a stable hash in the
 * browser and send that as `passwordHash` to the API. The server then verifies
 * that value against its stored scrypt hash.
 */

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
  const digest = await (globalThis.crypto || (window as any).crypto).subtle.digest("SHA-256", data)
  return toBase64Url(digest)
}
