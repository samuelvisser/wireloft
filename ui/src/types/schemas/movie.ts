import {z} from "zod";
import {MovieExtraTypeSchema} from './dailywire_catalog'
import {ApiDateTimeSchema} from './datetime'


export const MovieExtraCreateSchema = z.object({
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
    publishedDate: z.date().nullable().optional(),
    availableFor: z.array(z.string()).default([]),
})
export type MovieExtraCreateIn = z.input<typeof MovieExtraCreateSchema>;
export type MovieExtraCreateOut = z.output<typeof MovieExtraCreateSchema>;


export const MovieExtraReadSchema = z.looseObject({
    id: z.int(),
    movieId: z.int(),
    uuid: z.string(),
    slug: z.string(),
    title: z.string(),
    movieExtraType: MovieExtraTypeSchema,
    description: z.string().nullable(),
    downloadedDate: ApiDateTimeSchema.nullable(),
    duration: z.number(),
    backgroundImagePath: z.string().nullable(),
    thumbnailLandscapePath: z.string().nullable(),
    thumbnailPortraitPath: z.string().nullable(),
    thumbnailSquarePath: z.string().nullable(),
    sharingUrl: z.string().nullable(),
    publishedDate: ApiDateTimeSchema.nullable(),
    availableFor: z.array(z.string()),
    createdAt: ApiDateTimeSchema,
    updatedAt: ApiDateTimeSchema,
})
export type MovieExtraRead = z.infer<typeof MovieExtraReadSchema>;

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
    hasVideo: z.boolean().default(false),
    isDownloadable: z.boolean().nullable().optional(),
    status: z.string().nullable().optional(),
    publishedAt: z.date().nullable().optional(),
    background: z.string().nullable().optional(),
    byline: z.string().nullable().optional(),
    language: z.string().nullable().optional(),
    originCountry: z.string().nullable().optional(),
    images: z.record(z.string(), z.unknown()).default({}),
    availableFor: z.array(z.string()).default([]),
    castAndCrew: z.array(z.record(z.string(), z.unknown())).default([]),
    directedBy: z.array(z.string()).default([]),
    genres: z.array(z.unknown()).default([]),
    hosts: z.array(z.record(z.string(), z.unknown())).default([]),
    moreLikeThis: z.array(z.record(z.string(), z.unknown())).default([]),
    productionCompanies: z.array(z.unknown()).default([]),
    shopItems: z.array(z.unknown()).default([]),
    starring: z.array(z.string()).default([]),
    writtenBy: z.array(z.string()).default([]),
})

export const MovieCreateSchema = MovieBaseSchema.extend({
    slug: z.string(),
    movieExtras: z.array(MovieExtraCreateSchema).default([]),
    officialTrailerSlug: z.string().nullable().optional(),
})
export type MovieCreateIn = z.input<typeof MovieCreateSchema>;
export type MovieCreateOut = z.output<typeof MovieCreateSchema>;

export const MovieUpdateSchema = MovieBaseSchema.extend({})
export type MovieUpdateIn = z.input<typeof MovieUpdateSchema>;
export type MovieUpdateOut = z.output<typeof MovieUpdateSchema>;

export const MovieReadSchema = z.looseObject({
    id: z.int(),
    uuid: z.string(),
    slug: z.string(),
    title: z.string(),
    extendedTitle: z.string().nullable().optional(),
    description: z.string().nullable().optional(),
    downloadedDate: ApiDateTimeSchema.nullable().optional(),
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
    hasVideo: z.boolean(),
    isDownloadable: z.boolean().nullable(),
    status: z.string().nullable(),
    publishedAt: ApiDateTimeSchema.nullable(),
    background: z.string().nullable(),
    byline: z.string().nullable(),
    language: z.string().nullable(),
    originCountry: z.string().nullable(),
    images: z.record(z.string(), z.unknown()),
    availableFor: z.array(z.string()),
    castAndCrew: z.array(z.record(z.string(), z.unknown())),
    directedBy: z.array(z.string()),
    genres: z.array(z.unknown()),
    hosts: z.array(z.record(z.string(), z.unknown())),
    moreLikeThis: z.array(z.record(z.string(), z.unknown())),
    productionCompanies: z.array(z.unknown()),
    shopItems: z.array(z.unknown()),
    starring: z.array(z.string()),
    writtenBy: z.array(z.string()),
    // Calendar dates stay calendar dates. Do not invent midnight or a timezone.
    releaseDate: z.iso.date().nullable(),
    releaseDateSource: z.string().nullable(),
    releaseDateSourceId: z.string().nullable(),
    releaseDateLookupStatus: z.string(),
    releaseDateLookupAttemptedAt: ApiDateTimeSchema.nullable(),
    releaseDateLookupError: z.string().nullable(),
    officialTrailerId: z.int().nullable(),
    officialTrailer: MovieExtraReadSchema.nullable(),
    movieExtras: z.array(MovieExtraReadSchema),
    createdAt: ApiDateTimeSchema,
    updatedAt: ApiDateTimeSchema,
})
export type MovieRead = z.infer<typeof MovieReadSchema>;
