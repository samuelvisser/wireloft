import {createSelectRegistry} from '../../utils/selectRegistry'
import type {DestinationRead, NotificationEventRead, ServiceFieldRead} from '../../types/schemas/notifications'

export const DeliveryReg = createSelectRegistry('NotificationDelivery', {
    now: {label: 'right away'},
    grouped: {label: 'grouped per Show, hourly'},
    daily: {label: 'in a daily summary'},
})

export const SharedScopeReg = createSelectRegistry('NotificationScope', {
    any: {label: 'any Show'},
    chosen: {label: 'these Shows'},
})

export const MethodReg = createSelectRegistry('WebhookMethod', {
    POST: {label: 'POST'},
    PUT: {label: 'PUT'},
})

export const RefreshScopeReg = createSelectRegistry('MediaServerRefresh', {
    folder: {label: 'Only the changed folder'},
    library: {label: 'The whole library'},
})

/** The things a rule can be about, in the order the API lists them. */
export function eventRegistry(events: NotificationEventRead[]) {
    return createSelectRegistry(
        'NotificationEvent',
        Object.fromEntries(events.map((event) => [event.event, {label: event.when}])),
        events.map((event) => event.event),
    )
}

export const DEFAULT_CHOICE = '__default'

/** An Apprise field with a fixed set of answers, plus "not set" when it may stay empty. */
export function fieldRegistry(field: ServiceFieldRead) {
    const spec: Record<string, {label: string}> = {}
    if (field.kind === 'boolean') {
        spec[DEFAULT_CHOICE] = {label: `Default${field.default ? ` (${field.default})` : ''}`}
        spec.yes = {label: 'Yes'}
        spec.no = {label: 'No'}
    } else {
        if (!field.required || !field.default) {
            spec[DEFAULT_CHOICE] = {label: field.default ? `Default (${field.default})` : 'Not set'}
        }
        for (const choice of field.choices) spec[choice.value] = {label: choice.label}
    }
    return createSelectRegistry(`AppriseField:${field.key}`, spec, Object.keys(spec))
}

export function scriptRegistry(scripts: string[]) {
    return createSelectRegistry('NotificationScript', Object.fromEntries(scripts.map((name) => [name, {label: name}])), scripts)
}

export const KIND_LABELS: Record<DestinationRead['kind'], string> = {
    apprise: 'Message',
    jellyfin: 'Jellyfin',
    emby: 'Emby',
    plex: 'Plex',
    webhook: 'Webhook',
    script: 'Script',
}
