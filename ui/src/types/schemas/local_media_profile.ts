import {z} from 'zod'

import {createServerErrorMapper} from '../../utils/serverMessageMap'
import {
    MovieLocalMediaProfileCreateSchema,
    MovieLocalMediaProfileReadSchema,
    MovieLocalMediaProfileUpdateSchema,
} from './movie_local_media_profile'
import {
    ShowLocalMediaProfileCreateSchema,
    ShowLocalMediaProfileReadSchema,
    ShowLocalMediaProfileUpdateSchema,
} from './show_local_media_profile'

export * from './local_media_profile_base'
export * from './movie_local_media_profile'
export * from './show_local_media_profile'


export const LocalMediaProfileServerErrors = createServerErrorMapper({
    name: {unique_violation: 'Name is already taken.'},
    slug: {unique_violation: 'Slug is already taken.'},
    outputTemplate: {
        unique_violation: 'A profile with these output settings already exists.',
    },
})


const DATE_OUTPUT_TEMPLATE_FIELDS = [
    'date', 'time', 'datetime', 'year', 'month', 'day', 'hour', 'minute', 'second',
] as const

export const SHOW_OUTPUT_TEMPLATE_FIELDS = [
    'show', 'show_title', 'season', 'season_name', 'season_index', 'episode', 'episode_title', 'title',
    'episode_type', 'episode_number', 'episode_label', 'episode_identifier', 'episode_published_date',
    'episode_published_time', 'episode_published_datetime',
    ...DATE_OUTPUT_TEMPLATE_FIELDS,
] as const

export const MOVIE_OUTPUT_TEMPLATE_FIELDS = [
    'movie_slug', 'movie_title', 'movie_extended_title', 'movie_dw_id', 'movie_author',
    'movie_mature_rating', 'movie_duration_seconds',
    'movie_date', 'movie_time', 'movie_datetime', 'movie_year', 'movie_month', 'movie_day',
    'movie_hour', 'movie_minute', 'movie_second',
    'slug', 'title', 'extended_title', 'dw_id', 'author', 'mature_rating', 'rating',
    'duration_seconds', 'media_type',
    ...DATE_OUTPUT_TEMPLATE_FIELDS,
] as const


// ---------- Strict request (create/update) ----------
export const LocalMediaProfileCreateSchema = z.discriminatedUnion('type', [
    ShowLocalMediaProfileCreateSchema,
    MovieLocalMediaProfileCreateSchema,
])
export type LocalMediaProfileCreateIn = z.input<typeof LocalMediaProfileCreateSchema>
export type LocalMediaProfileCreateOut = z.output<typeof LocalMediaProfileCreateSchema>

export const LocalMediaProfileUpdateSchema = z.discriminatedUnion('type', [
    ShowLocalMediaProfileUpdateSchema,
    MovieLocalMediaProfileUpdateSchema,
])
export type LocalMediaProfileUpdateIn = z.input<typeof LocalMediaProfileUpdateSchema>
export type LocalMediaProfileUpdateOut = z.output<typeof LocalMediaProfileUpdateSchema>


// ------------ Lenient response (read) ------------
export const LocalMediaProfileReadSchema = z.discriminatedUnion('type', [
    ShowLocalMediaProfileReadSchema,
    MovieLocalMediaProfileReadSchema,
])
export type LocalMediaProfileRead = z.infer<typeof LocalMediaProfileReadSchema>
