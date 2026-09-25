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


export const SHOW_LOCAL_MEDIA_PROFILE_INDEXING_VALUES_MAX_ITEMS = 100

export const ShowLocalMediaProfileIndexingValuesSchema = z.array(IndexingValueEntrySchema)
    .max(
        SHOW_LOCAL_MEDIA_PROFILE_INDEXING_VALUES_MAX_ITEMS,
        `At most ${SHOW_LOCAL_MEDIA_PROFILE_INDEXING_VALUES_MAX_ITEMS} Indexing Values are allowed`,
    )
    .superRefine((indexingValues, ctx) => {
        const seen = new Set<string>()
        indexingValues.forEach(({key}, index) => {
            if (seen.has(key)) {
                ctx.addIssue({
                    code: 'custom',
                    path: [index, 'key'],
                    message: 'Keys must be unique',
                })
            }
            seen.add(key)
        })
    })


// ---------- Strict request (create/update) ----------
const ShowLocalMediaProfileBaseSchema = LocalMediaProfileSchemaRequest.extend({
    type: z.literal('show').default('show'),
    showScope: z.enum(ShowLocalMediaProfileScopeReg.values).default('both'),
    outputTemplate: LocalMediaProfileOutputTemplateSchema.default(
        '/downloads/shows/{{ show }}/{{ episode_title }}.ext',
    ),
    preferredFormat: z.enum(PreferredFormatReg.values).default('format_audio_only'),
    indexingValues: ShowLocalMediaProfileIndexingValuesSchema.default([]),
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
