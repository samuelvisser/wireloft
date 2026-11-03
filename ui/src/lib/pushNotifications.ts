import {z} from 'zod'

import {PushDeviceStatusReadSchema} from '../types/schemas/notifications'
import {errorMessage} from './notifications'

const PushPublicKeySchema = z.object({publicKey: z.string()})

function apiBase(): string {
    return ((window as any).appConfig?.API_URL || '/api').replace(/\/+$/, '')
}

async function pushFetch(path: string, method = 'GET', body?: unknown): Promise<unknown> {
    const response = await fetch(`${apiBase()}/push${path}`, {
        method,
        credentials: 'include',
        cache: 'no-store',
        headers: body !== undefined ? {'Content-Type': 'application/json'} : undefined,
        body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    if (!response.ok) throw new Error(await errorMessage(response))
    if (response.status === 204) return null
    return response.json()
}

/** Push needs the built app over HTTPS (or localhost), with a service worker. */
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

function deviceName(): string {
    const agent = navigator.userAgent
    const system = /iPhone|iPad/.test(agent) ? 'iPhone or iPad' : /Android/.test(agent) ? 'Android'
        : /Mac/.test(agent) ? 'Mac' : /Windows/.test(agent) ? 'Windows' : /Linux/.test(agent) ? 'Linux' : 'This device'
    const browser = /Edg\//.test(agent) ? 'Edge' : /Firefox\//.test(agent) ? 'Firefox'
        : /Chrome\//.test(agent) ? 'Chrome' : /Safari\//.test(agent) ? 'Safari' : ''
    return browser ? `${browser} on ${system}` : system
}

function subscriptionPayload(subscription: PushSubscription) {
    const json = subscription.toJSON()
    if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) {
        throw new Error('The browser did not provide valid subscription keys')
    }
    return {endpoint: json.endpoint, keys: {p256dh: json.keys.p256dh, auth: json.keys.auth}, deviceName: deviceName()}
}

/** Whether this browser already gets push messages for whoever is signed in. */
export async function pushIsOn(subscription: PushSubscription): Promise<boolean> {
    return PushDeviceStatusReadSchema.parse(await pushFetch('/lookup', 'POST', {endpoint: subscription.endpoint})).subscribed
}

export async function enablePush(): Promise<PushSubscription> {
    if (!supportsPush()) throw new Error('Push is not available in this browser')
    // Ask for permission straight from the click, before any other waiting.
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') throw new Error('Notifications are blocked for WireLoft in this browser')

    const registration = await navigator.serviceWorker.register('/sw.js', {scope: '/', updateViaCache: 'none'})
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
        PushDeviceStatusReadSchema.parse(await pushFetch('/subscribe', 'POST', subscriptionPayload(subscription)))
    } catch (error) {
        if (created) await subscription.unsubscribe()
        throw error
    }
    return subscription
}

export async function disablePush(subscription: PushSubscription): Promise<void> {
    await pushFetch('/unsubscribe', 'POST', {endpoint: subscription.endpoint})
    await subscription.unsubscribe()
}

export async function sendTestPush(subscription: PushSubscription): Promise<void> {
    await pushFetch('/test', 'POST', {endpoint: subscription.endpoint})
}
