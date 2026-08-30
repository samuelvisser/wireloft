import {z} from "zod";
import {createServerErrorMapper} from "../../utils/serverMessageMap";
import {MoviePreferredFormatReg, PreferredFormatReg} from "../local_media_profile";

export const LocalMediaProfileServerErrors = createServerErrorMapper({
    name: {unique_violation: "Name is already taken."},
    slug: {unique_violation: "Slug is already taken."},
    outputTemplate: {
        unique_violation: "A profile with these output settings already exists.",
    },
});

const outputTemplateSchema = (allowedFields: readonly string[]) => z.string()
    .regex(/^\/downloads\//, "Output template must start with '/downloads/'")
    .regex(/\.ext$/, "Output template must end with '.ext'")
    .min(16)
    .superRefine((value, ctx) => {
        const placeholders = [...value.matchAll(/\{([^{}]+)}/g)].map((match) => match[1])
        const unsupported = [...new Set(placeholders.filter((field) => !allowedFields.includes(field)))].sort()
        if (unsupported.length) {
            ctx.addIssue({
                code: 'custom',
                message: `Unsupported placeholder(s): ${unsupported.map((field) => `{${field}}`).join(', ')}`,
            })
        }
    })

const DATE_OUTPUT_TEMPLATE_FIELDS = [
    'date', 'time', 'datetime', 'year', 'month', 'day', 'hour', 'minute', 'second',
] as const

export const SHOW_OUTPUT_TEMPLATE_FIELDS = [
    'show', 'show_title', 'season', 'season_name', 'episode', 'episode_title', 'title',
    'episode_type', 'episode_number', 'ep_id', 'episode_published_date',
    'episode_published_time', 'episode_published_datetime',
    ...DATE_OUTPUT_TEMPLATE_FIELDS,
] as const

export const MOVIE_OUTPUT_TEMPLATE_FIELDS = [
    'movie', 'movie_slug', 'movie_title', 'title', 'movie_extended_title', 'extended_title',
    'movie_dw_id', 'dw_id', 'movie_author', 'author', 'movie_mature_rating', 'mature_rating',
    'rating', 'movie_duration_seconds', 'duration_seconds', 'media_type',
    ...DATE_OUTPUT_TEMPLATE_FIELDS,
] as const

const MOVIE_MEDIA_ITEM_OUTPUT_TEMPLATE_FIELDS = new Set([
    'title', 'extended_title', 'dw_id', 'author', 'mature_rating', 'rating',
    'duration_seconds', 'media_type',
])

const TRAILER_COLLISION_MESSAGE =
    "Movie and trailer downloads could resolve to the same file. Enable 'Append media type to filename' (recommended), or include at least one placeholder that describes the actual downloaded item, such as {title}, {dw_id}, {duration_seconds}, or {media_type}."

const LocalMediaProfileCommonSchema = z.object({
    name: z.string().min(1, "Name is required"),
})

export const ShowLocalMediaProfileCreateSchema = LocalMediaProfileCommonSchema.extend({
    type: z.literal('show'),
    outputTemplate: outputTemplateSchema(SHOW_OUTPUT_TEMPLATE_FIELDS),
    preferredFormat: z.enum(PreferredFormatReg.values).default('format_audio_only'),
    appendMediaTypeToFilename: z.boolean().default(true),
})

const MovieLocalMediaProfileBaseSchema = LocalMediaProfileCommonSchema.extend({
    type: z.literal('movie'),
    outputTemplate: outputTemplateSchema(MOVIE_OUTPUT_TEMPLATE_FIELDS),
    preferredFormat: z.enum(MoviePreferredFormatReg.values).default('format_1080p'),
    appendMediaTypeToFilename: z.boolean().default(true),
})

function validateMovieFilenameSafety(
    value: {outputTemplate: string; appendMediaTypeToFilename: boolean},
    ctx: z.RefinementCtx,
) {
    if (value.appendMediaTypeToFilename) return
    const placeholders = [...value.outputTemplate.matchAll(/\{([^{}]+)}/g)].map((match) => match[1])
    if (!placeholders.some((field) => MOVIE_MEDIA_ITEM_OUTPUT_TEMPLATE_FIELDS.has(field))) {
        ctx.addIssue({
            code: 'custom',
            path: ['outputTemplate'],
            message: TRAILER_COLLISION_MESSAGE,
        })
    }
}

export const MovieLocalMediaProfileCreateSchema = MovieLocalMediaProfileBaseSchema.superRefine(validateMovieFilenameSafety)

export const LocalMediaProfileCreateSchema = z.discriminatedUnion('type', [
    ShowLocalMediaProfileCreateSchema,
    MovieLocalMediaProfileCreateSchema,
])
export type LocalMediaProfileCreateIn = z.input<typeof LocalMediaProfileCreateSchema>;
export type LocalMediaProfileCreateOut = z.output<typeof LocalMediaProfileCreateSchema>;

export const ShowLocalMediaProfileUpdateSchema = ShowLocalMediaProfileCreateSchema.extend({
    id: z.int(),
    slug: z.string(),
})

export const MovieLocalMediaProfileUpdateSchema = MovieLocalMediaProfileBaseSchema.extend({
    id: z.int(),
    slug: z.string(),
}).superRefine(validateMovieFilenameSafety)

export const LocalMediaProfileUpdateSchema = z.discriminatedUnion('type', [
    ShowLocalMediaProfileUpdateSchema,
    MovieLocalMediaProfileUpdateSchema,
])
export type LocalMediaProfileUpdateIn = z.input<typeof LocalMediaProfileUpdateSchema>;
export type LocalMediaProfileUpdateOut = z.output<typeof LocalMediaProfileUpdateSchema>;


export const LocalMediaProfileReadSchema = z.looseObject({
    id: z.int(),
    type: z.enum(['show', 'movie']),
    slug: z.string(),
    name: z.string(),
    outputTemplate: z.string(),
    preferredFormat: z.union([z.enum(PreferredFormatReg.values), z.string()]),
    appendMediaTypeToFilename: z.boolean().default(true),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type LocalMediaProfileRead = z.infer<typeof LocalMediaProfileReadSchema>;
