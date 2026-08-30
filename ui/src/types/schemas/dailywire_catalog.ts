import {z} from 'zod'

const nullableString = z.string().nullable().optional()

export const DailywireCatalogShowReadSchema = z.looseObject({
    dwId: z.string(),
    slug: z.string(),
    title: z.string(),
    extendedTitle: nullableString,
    description: nullableString,
    authorName: nullableString,
    authorSlug: nullableString,
    authorHeadshotPath: nullableString,
    backgroundImagePath: nullableString,
    logoImagePath: nullableString,
    thumbnailLandscapePath: nullableString,
    thumbnailPortraitPath: nullableString,
    thumbnailSquarePath: nullableString,
})
export type DailywireCatalogShowRead = z.infer<typeof DailywireCatalogShowReadSchema>

export const DailywireCatalogMovieReadSchema = z.looseObject({
    dwId: z.string(),
    slug: z.string(),
    title: z.string(),
    description: nullableString,
    authorName: nullableString,
    authorSlug: nullableString,
    backgroundImagePath: nullableString,
    logoImagePath: nullableString,
    thumbnailLandscapePath: nullableString,
    thumbnailPortraitPath: nullableString,
    thumbnailSquarePath: nullableString,
})
export type DailywireCatalogMovieRead = z.infer<typeof DailywireCatalogMovieReadSchema>

export const MovieExtraTypeSchema = z.enum([
    'behindthescenes',
    'deleted',
    'featurette',
    'interview',
    'scene',
    'short',
    'trailer',
    'other',
])
export type MovieExtraType = z.infer<typeof MovieExtraTypeSchema>

export const DailywireMovieExtraReadSchema = z.looseObject({
    dwId: nullableString,
    slug: z.string(),
    title: z.string(),
    movieExtraType: MovieExtraTypeSchema,
    description: nullableString,
    sharingUrl: nullableString,
    duration: z.number(),
    backgroundImagePath: nullableString,
    thumbnailLandscapePath: nullableString,
    thumbnailPortraitPath: nullableString,
    thumbnailSquarePath: nullableString,
})
export type DailywireMovieExtraRead = z.infer<typeof DailywireMovieExtraReadSchema>

export const DailywireMovieReadSchema = DailywireCatalogMovieReadSchema.extend({
    duration: z.number(),
    sharingUrl: z.string(),
    matureRating: nullableString,
    isDownloadable: z.boolean(),
    availableFor: z.array(z.string()),
    movieExtras: z.array(DailywireMovieExtraReadSchema),
    trailer: DailywireMovieExtraReadSchema.nullable().optional(),
})
export type DailywireMovieRead = z.infer<typeof DailywireMovieReadSchema>

export const DailywireCatalogReadSchema = z.looseObject({
    shows: z.array(DailywireCatalogShowReadSchema),
    movies: z.array(DailywireCatalogMovieReadSchema),
})
export type DailywireCatalogRead = z.infer<typeof DailywireCatalogReadSchema>

export const DailywireCatalogShowPageReadSchema = z.looseObject({
    items: z.array(DailywireCatalogShowReadSchema),
    offset: z.number(),
    limit: z.number(),
    total: z.number(),
    hasMore: z.boolean(),
})
export type DailywireCatalogShowPageRead = z.infer<typeof DailywireCatalogShowPageReadSchema>

export const DailywireCatalogMoviePageReadSchema = z.looseObject({
    items: z.array(DailywireCatalogMovieReadSchema),
    offset: z.number(),
    limit: z.number(),
    total: z.number(),
    hasMore: z.boolean(),
})
export type DailywireCatalogMoviePageRead = z.infer<typeof DailywireCatalogMoviePageReadSchema>
