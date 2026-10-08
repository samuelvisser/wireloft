import {keepPreviousData, useQuery} from '@tanstack/react-query'

import {
    ChannelTestReadSchema,
    DestinationPreviewReadSchema,
    NotificationChannelReadSchema,
    NotificationDeliveryReadSchema,
    NotificationEventReadSchema,
    NotificationServiceReadSchema,
    type ChannelFormValues,
    type ChannelTestRead,
    type DestinationPreviewRead,
    type NotificationChannelRead,
    type NotificationDeliveryRead,
    type NotificationEventRead,
    type NotificationServiceRead,
} from '../types/schemas/notifications'

const apiUrl = (path: string) => `${(window as any).appConfig.API_URL}/notifications${path}`

async function fetchParsed<T>(path: string, schema: {parse(value: unknown): T}, signal?: AbortSignal): Promise<T> {
    const response = await fetch(apiUrl(path), {signal, credentials: 'include'})
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return schema.parse(await response.json())
}

export function sendJson(path: string, method: string, body?: unknown): Promise<Response> {
    return fetch(apiUrl(path), {
        method,
        credentials: 'include',
        headers: body === undefined ? undefined : {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body),
    })
}

async function parsedOrThrow<T>(response: Response, schema: {parse(value: unknown): T}, failure: string): Promise<T> {
    if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(typeof body?.detail === 'string' ? body.detail : failure)
    }
    return schema.parse(await response.json())
}

export const notificationQueryKeys = {
    events: ['notifications', 'events'] as const,
    services: ['notifications', 'services'] as const,
    channels: ['notifications', 'channels'] as const,
    deliveries: ['notifications', 'deliveries'] as const,
}

export function useNotificationEvents() {
    return useQuery<NotificationEventRead[], Error>({
        queryKey: notificationQueryKeys.events,
        queryFn: ({signal}) => fetchParsed('/events', NotificationEventReadSchema.array(), signal),
        staleTime: Infinity,
    })
}

export function useNotificationServices(enabled: boolean) {
    return useQuery<NotificationServiceRead[], Error>({
        queryKey: notificationQueryKeys.services,
        queryFn: ({signal}) => fetchParsed('/services', NotificationServiceReadSchema.array(), signal),
        staleTime: Infinity,
        enabled,
    })
}

export function useNotificationChannels() {
    return useQuery<NotificationChannelRead[], Error>({
        queryKey: notificationQueryKeys.channels,
        queryFn: ({signal}) => fetchParsed('/channels', NotificationChannelReadSchema.array(), signal),
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
    })
}

export function useNotificationDeliveries(enabled: boolean) {
    return useQuery<NotificationDeliveryRead[], Error>({
        queryKey: notificationQueryKeys.deliveries,
        queryFn: ({signal}) => fetchParsed('/deliveries?limit=50', NotificationDeliveryReadSchema.array(), signal),
        refetchInterval: 10_000,
        refetchOnMount: 'always',
        enabled,
    })
}

/** The destination part of the channel form as the API expects it, or undefined to keep the stored one. */
export function destinationPayload(form: ChannelFormValues) {
    if (form.changeDestination === false) return undefined
    return form.mode === 'url'
        ? {mode: 'url', url: (form.url ?? '').trim()}
        : {mode: 'fields', service: form.service, values: form.values ?? {}}
}

export async function previewDestination(form: ChannelFormValues, signal?: AbortSignal): Promise<DestinationPreviewRead> {
    const response = await fetch(apiUrl('/destinations/preview'), {
        method: 'POST',
        signal,
        credentials: 'include',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({destination: destinationPayload(form)}),
    })
    return parsedOrThrow(response, DestinationPreviewReadSchema, 'Could not build the destination')
}

export async function testDestination(form: ChannelFormValues): Promise<ChannelTestRead> {
    const response = await sendJson('/destinations/test', 'POST', {destination: destinationPayload(form)})
    return parsedOrThrow(response, ChannelTestReadSchema, 'Could not send the test notification')
}

export async function testChannel(channelId: number): Promise<ChannelTestRead> {
    return parsedOrThrow(await sendJson(`/channels/${channelId}/test`, 'POST'), ChannelTestReadSchema, 'Could not send the test notification')
}

export async function setChannelEnabled(channelId: number, enabled: boolean): Promise<void> {
    const response = await sendJson(`/channels/${channelId}`, 'PATCH', {enabled})
    if (!response.ok) throw new Error('Could not update the channel')
}

export async function deleteChannel(channelId: number): Promise<void> {
    const response = await sendJson(`/channels/${channelId}`, 'DELETE')
    if (!response.ok) throw new Error('Could not delete the channel')
}

export async function saveRouting(routes: {channelId: number; events: string[]}[]): Promise<void> {
    const response = await sendJson('/routing', 'PUT', {routes})
    if (!response.ok) throw new Error('Could not save routing')
}
