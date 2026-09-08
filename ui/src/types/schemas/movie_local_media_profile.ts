import {z} from 'zod'

import {MoviePreferredFormatReg} from '../local_media_profile'
import {
    LocalMediaProfileCreateBaseSchema,
    LocalMediaProfileOutputTemplateSchema,
    LocalMediaProfileSchemaRequest,
    LocalMediaProfileSchemaResponse,
    LocalMediaProfileUpdateBaseSchema,
} from './local_media_profile_base'


// ---------- Strict request (create/update) ----------
const MovieLocalMediaProfileBaseSchema = LocalMediaProfileSchemaRequest.extend({
    type: z.literal('movie').default('movie'),
    outputTemplate: LocalMediaProfileOutputTemplateSchema.default(
        "/downloads/movies/{{ movie_title }}/{{ title }}{% if media_type != 'movie' %}-{{ media_type }}{% endif %}.ext",
    ),
    preferredFormat: z.enum(MoviePreferredFormatReg.values).default('format_1080p'),
})

export const MovieLocalMediaProfileCreateSchema = MovieLocalMediaProfileBaseSchema.extend(
    LocalMediaProfileCreateBaseSchema.shape,
)
export type MovieLocalMediaProfileCreateIn = z.input<typeof MovieLocalMediaProfileCreateSchema>
export type MovieLocalMediaProfileCreateOut = z.output<typeof MovieLocalMediaProfileCreateSchema>

export const MovieLocalMediaProfileUpdateSchema = MovieLocalMediaProfileBaseSchema.extend(
    LocalMediaProfileUpdateBaseSchema.shape,
)
export type MovieLocalMediaProfileUpdateIn = z.input<typeof MovieLocalMediaProfileUpdateSchema>
export type MovieLocalMediaProfileUpdateOut = z.output<typeof MovieLocalMediaProfileUpdateSchema>


// ------------ Lenient response (read) ------------
export const MovieLocalMediaProfileReadSchema = LocalMediaProfileSchemaResponse.safeExtend({
    type: z.literal('movie'),
})
export type MovieLocalMediaProfileRead = z.infer<typeof MovieLocalMediaProfileReadSchema>
