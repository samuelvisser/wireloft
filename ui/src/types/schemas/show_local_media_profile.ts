import {z} from 'zod'

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
})

export const ShowLocalMediaProfileCreateSchema = ShowLocalMediaProfileBaseSchema.extend(
    LocalMediaProfileCreateBaseSchema.shape,
)
export type ShowLocalMediaProfileCreateIn = z.input<typeof ShowLocalMediaProfileCreateSchema>
export type ShowLocalMediaProfileCreateOut = z.output<typeof ShowLocalMediaProfileCreateSchema>

export const ShowLocalMediaProfileUpdateSchema = ShowLocalMediaProfileBaseSchema.extend(
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
})
export type ShowLocalMediaProfileRead = z.infer<typeof ShowLocalMediaProfileReadSchema>
