import {z} from 'zod'

const PushDeviceSettingsSchema = z.object({
  enabled: z.boolean(),
  events: z.array(z.string()),
})
const PushPublicKeySchema = z.object({publicKey: z.string()})

export const DEFAULT_PUSH_EVENTS = ['download_failed', 'task_failed']

function apiBase(): string {
  return (window as any).appConfig?.API_URL || '/api'
}

async function pushFetch(path: string, method = 'GET', body?: unknown): Promise<unknown> {
  const response = await fetch(`${apiBase()}/push${path}`, {
    method,
    credentials: 'include',
    cache: 'no-store',
    headers: body !== undefined ? {'Content-Type': 'application/json'} : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) throw new Error(`Push settings request failed (HTTP ${response.status})`)
  if (response.status === 204) return null
  return response.json()
}

export function supportsPush(): boolean {
  return import.meta.env.PROD
    && window.isSecureContext
    && 'serviceWorker' in navigator
    && 'PushManager' in window
    && 'Notification' in window
}

export async function existingPushSubscription(): Promise<PushSubscription | null> {
  if (!supportsPush()) return null
  const registration = await navigator.serviceWorker.getRegistration('/')
  return registration ? registration.pushManager.getSubscription() : null
}

function applicationServerKey(base64url: string): ArrayBuffer {
  const decoded = atob(base64url.replace(/-/g, '+').replace(/_/g, '/'))
  const bytes = new Uint8Array(decoded.length)
  for (let i = 0; i < decoded.length; i++) bytes[i] = decoded.charCodeAt(i)
  return bytes.buffer as ArrayBuffer
}

function subscriptionPayload(subscription: PushSubscription, events: string[]) {
  const json = subscription.toJSON()
  if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) {
    throw new Error('The browser did not provide valid subscription keys')
  }
  return {
    endpoint: json.endpoint,
    keys: {p256dh: json.keys.p256dh, auth: json.keys.auth},
    events,
  }
}

export async function pushDeviceSettings(subscription: PushSubscription): Promise<{
  enabled: boolean
  events: string[]
}> {
  return PushDeviceSettingsSchema.parse(await pushFetch(
    '/subscription-settings', 'POST', {endpoint: subscription.endpoint},
  ))
}

export async function enablePush(events: string[]): Promise<PushSubscription> {
  if (!supportsPush()) throw new Error('Push is not available in this browser')
  // Request permission directly from the user's click, before asynchronous IO.
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') throw new Error('Notification permission was not granted')

  const registration = await navigator.serviceWorker.register('/sw.js', {
    scope: '/',
    updateViaCache: 'none',
  })
  let subscription = await registration.pushManager.getSubscription()
  const created = subscription === null
  if (!subscription) {
    const {publicKey} = PushPublicKeySchema.parse(await pushFetch('/vapid-key'))
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: applicationServerKey(publicKey),
    })
  }

  try {
    PushDeviceSettingsSchema.parse(await pushFetch(
      '/subscriptions', 'POST', subscriptionPayload(subscription, events),
    ))
  } catch (error) {
    if (created) await subscription.unsubscribe()
    throw error
  }
  return subscription
}

export async function savePushEvents(subscription: PushSubscription, events: string[]): Promise<void> {
  PushDeviceSettingsSchema.parse(await pushFetch(
    '/subscriptions', 'POST', subscriptionPayload(subscription, events),
  ))
}

export async function disablePush(subscription: PushSubscription): Promise<void> {
  await pushFetch('/subscriptions', 'DELETE', {endpoint: subscription.endpoint})
  await subscription.unsubscribe()
}
