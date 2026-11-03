import {z} from 'zod'

import {ApiDateTimeSchema} from './datetime'

// ---------- Read models ----------
export const NotificationEventReadSchema = z.object({
    event: z.string(),
    when: z.string(),
    tone: z.enum(['success', 'failure', 'info']),
    shows: z.boolean(),
    actions: z.boolean(),
    problem: z.boolean(),
})
export type NotificationEventRead = z.infer<typeof NotificationEventReadSchema>

export const ServiceFieldReadSchema = z.object({
    key: z.string(),
    label: z.string(),
    kind: z.enum(['text', 'secret', 'number', 'select', 'boolean', 'list']),
    required: z.boolean(),
    advanced: z.boolean(),
    choices: z.array(z.object({value: z.string(), label: z.string()})),
    default: z.string().nullable(),
})
export type ServiceFieldRead = z.infer<typeof ServiceFieldReadSchema>

export const AppriseServiceReadSchema = z.object({
    key: z.string(),
    name: z.string(),
    serviceUrl: z.string().nullable(),
    setupUrl: z.string().nullable(),
    fields: z.array(ServiceFieldReadSchema),
})
export type AppriseServiceRead = z.infer<typeof AppriseServiceReadSchema>

export const DestinationKindSchema = z.enum(['apprise', 'jellyfin', 'emby', 'plex', 'webhook', 'script'])
export type DestinationKind = z.infer<typeof DestinationKindSchema>

export const DestinationHealthSchema = z.enum(['healthy', 'failing', 'untested', 'disabled'])
export type DestinationHealth = z.infer<typeof DestinationHealthSchema>

export const DestinationReadSchema = z.object({
    id: z.number().int(),
    kind: DestinationKindSchema,
    purpose: z.enum(['message', 'action']),
    name: z.string(),
    service: z.string(),
    serviceName: z.string(),
    masked: z.string(),
    enabled: z.boolean(),
    health: DestinationHealthSchema,
    lastError: z.string().nullable(),
    lastAttemptAt: ApiDateTimeSchema.nullable(),
    lastSuccessAt: ApiDateTimeSchema.nullable(),
    settings: z.record(z.string(), z.unknown()),
})
export type DestinationRead = z.infer<typeof DestinationReadSchema>

export const TestReadSchema = z.object({
    delivered: z.boolean(),
    error: z.string().nullable(),
    elapsedMs: z.number().int(),
})
export type TestRead = z.infer<typeof TestReadSchema>

export const DestinationPreviewReadSchema = z.object({
    service: z.string(),
    serviceName: z.string(),
    masked: z.string(),
})
export type DestinationPreviewRead = z.infer<typeof DestinationPreviewReadSchema>

export const RuleReadSchema = z.object({
    id: z.number().int(),
    defaultKey: z.string().nullable(),
    enabled: z.boolean(),
    event: z.string(),
    showScope: z.enum(['any', 'chosen']),
    showIds: z.array(z.number().int()),
    push: z.boolean(),
    destinationIds: z.array(z.number().int()),
    delivery: z.enum(['now', 'grouped', 'daily']),
    summaryTime: z.string(),
})
export type RuleRead = z.infer<typeof RuleReadSchema>

export const ScriptsReadSchema = z.object({
    folder: z.string(),
    scripts: z.array(z.string()),
    variables: z.array(z.string()),
})
export type ScriptsRead = z.infer<typeof ScriptsReadSchema>

export const DeliveryReadSchema = z.object({
    id: z.number().int(),
    title: z.string(),
    event: z.string(),
    destination: z.string(),
    status: z.enum(['PENDING', 'SENT', 'FAILED', 'CANCELED']),
    error: z.string().nullable(),
    at: ApiDateTimeSchema,
    /** When a failed attempt is tried again; only while it waits for that. */
    retryAt: ApiDateTimeSchema.nullable().optional(),
})
export type DeliveryRead = z.infer<typeof DeliveryReadSchema>

export const DeviceReadSchema = z.object({
    id: z.number().int(),
    deviceName: z.string(),
    createdAt: ApiDateTimeSchema,
})
export type DeviceRead = z.infer<typeof DeviceReadSchema>

export const PushDeviceStatusReadSchema = z.object({
    subscribed: z.boolean(),
    deviceId: z.number().int().nullable().optional(),
})

export const WebhookExampleReadSchema = z.object({payload: z.record(z.string(), z.unknown())})

// ---------- Add / edit a destination ----------
const FieldValuesSchema = z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.array(z.string())]))
export type FieldValues = z.infer<typeof FieldValuesSchema>

export const DestinationFormSchema = z.object({
    name: z.string().trim().min(1, 'Give it a name').max(80, 'Use at most 80 characters'),
    kind: DestinationKindSchema.default('apprise'),
    // Apprise
    mode: z.enum(['fields', 'url']).default('fields'),
    service: z.string().default(''),
    values: FieldValuesSchema.default({}),
    url: z.string().trim().default(''),
    // Jellyfin, Emby and Plex
    address: z.string().trim().default(''),
    apiKey: z.string().trim().default(''),
    scope: z.enum(['folder', 'library']).default('folder'),
    pathFrom: z.string().trim().default(''),
    pathTo: z.string().trim().default(''),
    // Webhook
    webhookUrl: z.string().trim().default(''),
    method: z.enum(['POST', 'PUT']).default('POST'),
    secretHeader: z.string().trim().default(''),
    secretValue: z.string().default(''),
    // Script
    script: z.string().default(''),
    timeoutSeconds: z.coerce.number().int().min(1, 'At least 1 second').max(3600, 'At most an hour').default(60),
    // Editing keeps the stored settings unless they are entered again.
    changeSettings: z.boolean().default(true),
    // Carries server errors about the settings to the form.
    destination: z.string().optional(),
}).superRefine((form, ctx) => {
    if (!form.changeSettings) return
    const need = (path: string, message: string) => ctx.addIssue({code: 'custom', path: [path], message})
    if (form.kind === 'apprise') {
        if (form.mode === 'fields' && !form.service) need('service', 'Choose a service')
        if (form.mode === 'url' && !form.url.includes('://')) need('url', 'An Apprise URL looks like service://credentials')
    } else if (form.kind === 'webhook') {
        if (!/^https?:\/\//.test(form.webhookUrl)) need('webhookUrl', 'A webhook address starts with http:// or https://')
    } else if (form.kind === 'script') {
        if (!form.script) need('script', 'Choose a script')
    } else {
        if (!/^https?:\/\//.test(form.address)) need('address', 'The address looks like http://jellyfin:8096')
        if (!form.apiKey) need('apiKey', form.kind === 'plex' ? 'Enter the Plex token' : 'Enter an API key')
    }
})
export type DestinationFormValues = z.input<typeof DestinationFormSchema>

// ---------- Add / edit a rule ----------
export const RuleFormSchema = z.object({
    enabled: z.boolean().default(true),
    event: z.string().min(1, 'Choose what happens').default('episode_downloaded'),
    showScope: z.enum(['any', 'chosen']).default('any'),
    showIds: z.array(z.number().int()).default([]),
    push: z.boolean().default(true),
    destinationIds: z.array(z.number().int()).default([]),
    delivery: z.enum(['now', 'grouped', 'daily']).default('now'),
    summaryTime: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'Use a time like 08:00').default('08:00'),
}).superRefine((form, ctx) => {
    if (form.showScope === 'chosen' && form.showIds.length === 0) {
        ctx.addIssue({code: 'custom', path: ['showIds'], message: 'Choose at least one Show'})
    }
    if (form.event === 'everything' && form.delivery !== 'daily') {
        ctx.addIssue({code: 'custom', path: ['delivery'], message: 'Everything that happens only goes out in a daily summary'})
    }
})
export type RuleFormValues = z.input<typeof RuleFormSchema>
