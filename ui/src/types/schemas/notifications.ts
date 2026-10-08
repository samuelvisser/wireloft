import {z} from 'zod'

import {ApiDateTimeSchema} from './datetime'

// ---------- Read models ----------
export const NotificationEventReadSchema = z.object({
    event: z.string(),
    label: z.string(),
    description: z.string(),
    tone: z.enum(['success', 'failure', 'info', 'neutral']),
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

export const NotificationServiceReadSchema = z.object({
    key: z.string(),
    name: z.string(),
    serviceUrl: z.string().nullable(),
    setupUrl: z.string().nullable(),
    fields: z.array(ServiceFieldReadSchema),
})
export type NotificationServiceRead = z.infer<typeof NotificationServiceReadSchema>

export const ChannelHealthSchema = z.enum(['healthy', 'failing', 'untested', 'disabled'])
export type ChannelHealth = z.infer<typeof ChannelHealthSchema>

export const NotificationChannelReadSchema = z.object({
    id: z.number().int(),
    name: z.string(),
    service: z.string(),
    serviceName: z.string(),
    maskedUrl: z.string(),
    enabled: z.boolean(),
    health: ChannelHealthSchema,
    lastError: z.string().nullable(),
    lastAttemptAt: ApiDateTimeSchema.nullable(),
    lastSuccessAt: ApiDateTimeSchema.nullable(),
    events: z.array(z.string()),
})
export type NotificationChannelRead = z.infer<typeof NotificationChannelReadSchema>

export const ChannelTestReadSchema = z.object({
    delivered: z.boolean(),
    error: z.string().nullable(),
    elapsedMs: z.number().int(),
})
export type ChannelTestRead = z.infer<typeof ChannelTestReadSchema>

export const DestinationPreviewReadSchema = z.object({
    service: z.string(),
    serviceName: z.string(),
    maskedUrl: z.string(),
})
export type DestinationPreviewRead = z.infer<typeof DestinationPreviewReadSchema>

export const NotificationDeliveryReadSchema = z.object({
    id: z.string(),
    operationId: z.string(),
    title: z.string(),
    event: z.string(),
    destination: z.string(),
    status: z.enum(['PENDING', 'SENT', 'FAILED', 'CANCELED']),
    error: z.string().nullable(),
    at: ApiDateTimeSchema,
})
export type NotificationDeliveryRead = z.infer<typeof NotificationDeliveryReadSchema>

// ---------- Add / edit channel form ----------
const FieldValuesSchema = z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.array(z.string())]))
export type FieldValues = z.infer<typeof FieldValuesSchema>

export const ChannelFormSchema = z.object({
    name: z.string().trim().min(1, 'Give the channel a name').max(80, 'Use at most 80 characters'),
    mode: z.enum(['fields', 'url']).default('fields'),
    service: z.string().default(''),
    values: FieldValuesSchema.default({}),
    url: z.string().trim().default(''),
    // Editing keeps the stored destination unless the user chooses to replace it.
    changeDestination: z.boolean().default(true),
    // Carries server errors about the destination to the form.
    destination: z.string().optional(),
}).superRefine((form, ctx) => {
    if (!form.changeDestination) return
    if (form.mode === 'fields' && !form.service) {
        ctx.addIssue({code: 'custom', path: ['service'], message: 'Choose a service'})
    }
    if (form.mode === 'url' && !form.url.includes('://')) {
        ctx.addIssue({code: 'custom', path: ['url'], message: 'An Apprise URL looks like service://credentials'})
    }
})
export type ChannelFormValues = z.input<typeof ChannelFormSchema>
