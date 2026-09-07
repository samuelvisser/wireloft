import {z} from 'zod'
import {EpisodePublishStatus} from '../episode'


const EpisodeBaseSchema = z.object({
    publishStatus: z.enum(EpisodePublishStatus),
    wentLiveDate: z.date().optional(),
    publishedDate: z.date().optional(),
    redownloadedDate: z.date().optional(),
    title: z.string(),
    description: z.string(),
    downloadedDate: z.date().optional(),
})

export const EpisodeCreateSchema = EpisodeBaseSchema.extend({
    showId: z.int(),
    index: z.number(),
    dwId: z.string().optional(),
    slug: z.string(),
})
export type EpisodeCreateIn = z.input<typeof EpisodeCreateSchema>
export type EpisodeCreateOut = z.output<typeof EpisodeCreateSchema>

export const EpisodeUpdateSchema = EpisodeBaseSchema.extend({dwId: z.string().optional()})
export type EpisodeUpdateIn = z.input<typeof EpisodeUpdateSchema>
export type EpisodeUpdateOut = z.output<typeof EpisodeUpdateSchema>

export const EpisodeReadSchema = z.looseObject({
    id: z.int(),
    uuid: z.string(),
    dwId: z.string().optional(),
    showId: z.int(),
    seasonId: z.int(),
    index: z.number(),
    episodeIdentifier: z.string(),
    slug: z.string(),
    title: z.string(),
    publishStatus: z.union([z.enum(EpisodePublishStatus), z.string()]),
    earlyDeleteAvailable: z.boolean().optional().default(false),
    description: z.string(),
    backgroundImagePath: z.string().optional(),
    thumbnailLandscapePath: z.string().optional(),
    thumbnailPortraitPath: z.string().optional(),
    thumbnailSquarePath: z.string().optional(),
    wentLiveDate: z.iso.datetime().transform((s) => new Date(s)).optional(),
    publishedDate: z.iso.datetime().transform((s) => new Date(s)).optional(),
    redownloadedDate: z.iso.datetime().transform((s) => new Date(s)).optional(),
    downloadedDate: z.iso.datetime().transform((s) => new Date(s)).optional(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type EpisodeRead = z.infer<typeof EpisodeReadSchema>
