import {z} from "zod";
import {createServerErrorMapper} from "../../utils/serverMessageMap";
import {MoviePreferredFormatReg, PreferredFormatReg} from "../local_media_profile";

// Only override what you care about for this form.
export const LocalMediaProfileServerErrors = createServerErrorMapper({
    name: {unique_violation: "Name is already taken."},
    slug: {unique_violation: "Slug is already taken."},
    outputTemplate: {
        unique_violation: "A profile with this type, output path template, and preferred format already exists.",
    },
});

// ---------- Strict request (create/update) ----------
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

export const SHOW_OUTPUT_TEMPLATE_FIELDS = [
    'show', 'show_title', 'season', 'season_name', 'episode', 'episode_title', 'title',
    'episode_type', 'episode_number', 'ep_id', 'episode_published_date', 'date',
    'episode_published_time', 'time', 'episode_published_datetime', 'datetime',
] as const

export const MOVIE_OUTPUT_TEMPLATE_FIELDS = [
    'movie', 'movie_slug', 'movie_title', 'title', 'movie_extended_title', 'extended_title',
    'movie_dw_id', 'dw_id', 'movie_author', 'author', 'movie_mature_rating', 'mature_rating',
    'rating', 'movie_duration_seconds', 'duration_seconds',
] as const

const LocalMediaProfileCommonSchema = z.object({
    name: z.string().min(1, "Name is required"),
})

export const ShowLocalMediaProfileCreateSchema = LocalMediaProfileCommonSchema.extend({
    type: z.literal('show'),
    outputTemplate: outputTemplateSchema(SHOW_OUTPUT_TEMPLATE_FIELDS),
    preferredFormat: z.enum(PreferredFormatReg.values).default('format_audio_only'),
})

export const MovieLocalMediaProfileCreateSchema = LocalMediaProfileCommonSchema.extend({
    type: z.literal('movie'),
    outputTemplate: outputTemplateSchema(MOVIE_OUTPUT_TEMPLATE_FIELDS),
    preferredFormat: z.enum(MoviePreferredFormatReg.values).default('format_1080p'),
})

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

export const MovieLocalMediaProfileUpdateSchema = MovieLocalMediaProfileCreateSchema.extend({
    id: z.int(),
    slug: z.string(),
})

export const LocalMediaProfileUpdateSchema = z.discriminatedUnion('type', [
    ShowLocalMediaProfileUpdateSchema,
    MovieLocalMediaProfileUpdateSchema,
])
export type LocalMediaProfileUpdateIn = z.input<typeof LocalMediaProfileUpdateSchema>;
export type LocalMediaProfileUpdateOut = z.output<typeof LocalMediaProfileUpdateSchema>;


// ------------ Lenient response (read) ------------
export const LocalMediaProfileReadSchema = z.looseObject({
    id: z.int(),
    type: z.enum(['show', 'movie']),
    slug: z.string(),
    name: z.string(),
    outputTemplate: z.string(),
    preferredFormat: z.union([z.enum(PreferredFormatReg.values), z.string()]),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type LocalMediaProfileRead = z.infer<typeof LocalMediaProfileReadSchema>;
