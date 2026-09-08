import {z} from 'zod'
import {ApiDateTimeStringSchema} from './datetime'

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

const DailywireMovieExtraImagesSchema = z.looseObject({
    extraThumbnailImage: nullableString,
})

export const DailywireMovieExtraReadSchema = z.looseObject({
    dwId: nullableString,
    slug: z.string(),
    title: z.string(),
    movieExtraType: MovieExtraTypeSchema,
    description: nullableString,
    sharingUrl: nullableString,
    publishedDate: ApiDateTimeStringSchema.nullable(),
    duration: z.number(),
    availableFor: z.array(z.string()),
    images: DailywireMovieExtraImagesSchema,
    backgroundImagePath: nullableString,
    thumbnailLandscapePath: nullableString,
    thumbnailPortraitPath: nullableString,
    thumbnailSquarePath: nullableString,
    continueWatchingEntityId: nullableString,
    continueWatchingEntityType: nullableString,
    muxDrmToken: nullableString,
    muxPlaybackId: nullableString,
    muxPlaybackToken: nullableString,
    playbackPolicy: nullableString,
    trailerUrl: nullableString,
})
export type DailywireMovieExtraRead = z.infer<typeof DailywireMovieExtraReadSchema>

const DailywireMovieImagesSchema = z.looseObject({
    movieAppBackgroundImage: nullableString,
    movieLogoImage: nullableString,
    movieOttBackgroundImage: nullableString,
    moviePosterImage: nullableString,
    movieThumbnailImage: nullableString,
    movieWebBackgroundImage: nullableString,
})

export const DailywireMovieCastAndCrewReadSchema = z.looseObject({
    name: z.string(),
    imageSize: nullableString,
    imageUrl: nullableString,
    info: nullableString,
    roleText: nullableString,
})
export type DailywireMovieCastAndCrewRead = z.infer<typeof DailywireMovieCastAndCrewReadSchema>

const DailywireMovieHostImagesSchema = z.looseObject({
    hostAppBackgroundImage: nullableString,
    hostImage1x1: nullableString,
    hostLogoImage: nullableString,
    hostOttBackgroundImage: nullableString,
    hostWebBackgroundImage: nullableString,
})

export const DailywireMovieHostReadSchema = z.looseObject({
    images: DailywireMovieHostImagesSchema,
    dwId: nullableString,
    name: z.string(),
    slug: z.string(),
})
export type DailywireMovieHostRead = z.infer<typeof DailywireMovieHostReadSchema>

const DailywireRelatedContentImagesSchema = z.looseObject({
    movieAppBackgroundImage: nullableString,
    movieLogoImage: nullableString,
    movieOttBackgroundImage: nullableString,
    moviePosterImage: nullableString,
    movieThumbnailImage: nullableString,
    movieWebBackgroundImage: nullableString,
    showLogoImage: nullableString,
    showOttBackgroundImage: nullableString,
    showOttEpisodeBackgroundImage: nullableString,
    showPosterImage: nullableString,
    showThumbnailImage: nullableString,
    showWebBackgroundImage: nullableString,
})

export const DailywireRelatedContentReadSchema = z.looseObject({
    images: DailywireRelatedContentImagesSchema,
    contentType: z.string(),
    publishedAt: ApiDateTimeStringSchema.nullable(),
    slug: z.string(),
    title: z.string(),
})
export type DailywireRelatedContentRead = z.infer<typeof DailywireRelatedContentReadSchema>

export const DailywireMovieReadSchema = DailywireCatalogMovieReadSchema.extend({
    duration: z.number(),
    sharingUrl: z.string(),
    matureRating: nullableString,
    hasVideo: z.boolean(),
    isDownloadable: z.boolean(),
    status: z.string(),
    publishedAt: ApiDateTimeStringSchema.nullable(),
    background: nullableString,
    byline: nullableString,
    language: nullableString,
    originCountry: nullableString,
    images: DailywireMovieImagesSchema,
    availableFor: z.array(z.string()),
    castAndCrew: z.array(DailywireMovieCastAndCrewReadSchema),
    directedBy: z.array(z.string()),
    genres: z.array(z.unknown()),
    hosts: z.array(DailywireMovieHostReadSchema),
    moreLikeThis: z.array(DailywireRelatedContentReadSchema),
    productionCompanies: z.array(z.unknown()),
    shopItems: z.array(z.unknown()),
    starring: z.array(z.string()),
    writtenBy: z.array(z.string()),
    isUpcoming: z.boolean(),
    expectedReleaseDate: z.iso.date().nullable(),
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
