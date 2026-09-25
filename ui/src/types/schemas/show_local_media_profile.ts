import {z} from 'zod'
import {IndexingValueEntrySchema} from './custom_metadata'

import {PreferredFormatReg, ShowLocalMediaProfileScopeReg} from '../local_media_profile'
import {
    LocalMediaProfileCreateBaseSchema,
    LocalMediaProfileOutputTemplateSchema,
    LocalMediaProfileSchemaRequest,
    LocalMediaProfileSchemaResponse,
    LocalMediaProfileUpdateBaseSchema,
} from './local_media_profile_base'


// ---------- Strict request (create/update) ----------
const ShowLocalMediaProfileBaseSchema = LocalMediaProfileSchemaRequest.extend({
    type: z.literal('show').default('show'),
    showScope: z.enum(ShowLocalMediaProfileScopeReg.values).default('both'),
    outputTemplate: LocalMediaProfileOutputTemplateSchema.default(
        '/downloads/shows/{{ show }}/{{ episode_title }}.ext',
    ),
    preferredFormat: z.enum(PreferredFormatReg.values).default('format_audio_only'),
    indexingValues: z.array(IndexingValueEntrySchema).max(100).default([]),
}).superRefine(({indexingValues}, ctx) => {
    const seen = new Set<string>()
    indexingValues.forEach(({key}, index) => {
        if (seen.has(key)) ctx.addIssue({code: 'custom', path: ['indexingValues', index, 'key'], message: 'Keys must be unique'})
        seen.add(key)
    })
})

export const ShowLocalMediaProfileCreateSchema = ShowLocalMediaProfileBaseSchema.safeExtend(
    LocalMediaProfileCreateBaseSchema.shape,
)
export type ShowLocalMediaProfileCreateIn = z.input<typeof ShowLocalMediaProfileCreateSchema>
export type ShowLocalMediaProfileCreateOut = z.output<typeof ShowLocalMediaProfileCreateSchema>

export const ShowLocalMediaProfileUpdateSchema = ShowLocalMediaProfileBaseSchema.safeExtend(
    LocalMediaProfileUpdateBaseSchema.shape,
)
export type ShowLocalMediaProfileUpdateIn = z.input<typeof ShowLocalMediaProfileUpdateSchema>
export type ShowLocalMediaProfileUpdateOut = z.output<typeof ShowLocalMediaProfileUpdateSchema>


// ------------ Lenient response (read) ------------
export const ShowLocalMediaProfileReadSchema = LocalMediaProfileSchemaResponse.safeExtend({
    type: z.literal('show'),
    showScope: z.enum(ShowLocalMediaProfileScopeReg.values)
        .nullable()
        .optional()
        .transform((value) => value ?? 'both'),
    indexingValues: z.array(IndexingValueEntrySchema).default([]),
})
export type ShowLocalMediaProfileRead = z.infer<typeof ShowLocalMediaProfileReadSchema>
