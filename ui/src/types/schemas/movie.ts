import {z} from "zod";
import {MovieExtraTypeSchema} from './dailywire_catalog'


export const MovieExtraCreateSchema = z.object({
    dwId: z.string().nullable().optional(),
    slug: z.string(),
    title: z.string(),
    movieExtraType: MovieExtraTypeSchema,
    description: z.string().nullable().optional(),
    downloadedDate: z.date().nullable().optional(),
    duration: z.number().default(0),
    backgroundImagePath: z.string().nullable().optional(),
    thumbnailLandscapePath: z.string().nullable().optional(),
    thumbnailPortraitPath: z.string().nullable().optional(),
    thumbnailSquarePath: z.string().nullable().optional(),
    sharingUrl: z.string().nullable().optional(),
})
export type MovieExtraCreateIn = z.input<typeof MovieExtraCreateSchema>;
export type MovieExtraCreateOut = z.output<typeof MovieExtraCreateSchema>;


export const MovieExtraReadSchema = z.looseObject({
    id: z.int(),
    movieId: z.int(),
    uuid: z.string(),
    dwId: z.string().nullable(),
    slug: z.string(),
    title: z.string(),
    movieExtraType: MovieExtraTypeSchema,
    description: z.string().nullable(),
    downloadedDate: z.iso.datetime().transform((s) => new Date(s)).nullable(),
    duration: z.number(),
    backgroundImagePath: z.string().nullable(),
    thumbnailLandscapePath: z.string().nullable(),
    thumbnailPortraitPath: z.string().nullable(),
    thumbnailSquarePath: z.string().nullable(),
    sharingUrl: z.string().nullable(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type MovieExtraRead = z.infer<typeof MovieExtraReadSchema>;

// ---------- Strict request (create/update) ----------
const MovieBaseSchema = z.object({
    title: z.string(),
    extendedTitle: z.string().nullable().optional(),
    description: z.string().nullable().optional(),
    downloadedDate: z.date().nullable().optional(),
    duration: z.number().default(0),
    backgroundImagePath: z.string().nullable().optional(),
    thumbnailLandscapePath: z.string().nullable().optional(),
    thumbnailPortraitPath: z.string().nullable().optional(),
    thumbnailSquarePath: z.string().nullable().optional(),
    sharingUrl: z.string().nullable().optional(),
    authorName: z.string().nullable().optional(),
    authorSlug: z.string().nullable().optional(),
    logoImagePath: z.string().nullable().optional(),
    matureRating: z.string().nullable().optional(),
    isDownloadable: z.boolean().nullable().optional(),
    availableFor: z.array(z.string()).default([]),
})


export const MovieCreateSchema = MovieBaseSchema.extend({
    dwId: z.string().nullable().optional(),
    slug: z.string(),
    movieExtras: z.array(MovieExtraCreateSchema).default([]),
    officialTrailerSlug: z.string().nullable().optional(),
})
export type MovieCreateIn = z.input<typeof MovieCreateSchema>;
export type MovieCreateOut = z.output<typeof MovieCreateSchema>;


export const MovieUpdateSchema = MovieBaseSchema.extend({
})
export type MovieUpdateIn = z.input<typeof MovieUpdateSchema>;
export type MovieUpdateOut = z.output<typeof MovieUpdateSchema>;


// ------------ Lenient response (read) ------------
export const MovieReadSchema = z.looseObject({
    id: z.int(),
    uuid: z.string(),
    dwId: z.string().nullable().optional(),
    slug: z.string(),
    title: z.string(),
    extendedTitle: z.string().nullable().optional(),
    description: z.string().nullable().optional(),
    downloadedDate: z.iso.datetime().transform((s) => new Date(s)).nullable().optional(),
    duration: z.number(),
    backgroundImagePath: z.string().nullable(),
    thumbnailLandscapePath: z.string().nullable(),
    thumbnailPortraitPath: z.string().nullable(),
    thumbnailSquarePath: z.string().nullable(),
    sharingUrl: z.string().nullable(),
    authorName: z.string().nullable(),
    authorSlug: z.string().nullable(),
    logoImagePath: z.string().nullable(),
    matureRating: z.string().nullable(),
    isDownloadable: z.boolean().nullable(),
    availableFor: z.array(z.string()),
    releaseDate: z.iso.date().transform((s) => new Date(`${s}T00:00:00Z`)).nullable(),
    releaseDateSource: z.string().nullable(),
    releaseDateSourceId: z.string().nullable(),
    releaseDateLookupStatus: z.string(),
    releaseDateLookupAttemptedAt: z.iso.datetime().transform((s) => new Date(s)).nullable(),
    releaseDateLookupError: z.string().nullable(),
    officialTrailerId: z.int().nullable(),
    officialTrailer: MovieExtraReadSchema.nullable(),
    movieExtras: z.array(MovieExtraReadSchema),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type MovieRead = z.infer<typeof MovieReadSchema>;
