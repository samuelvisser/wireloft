import {z} from 'zod';
import {EpisodePublishStatus} from "../episode";
import {ApiDateTimeSchema} from "./datetime";


const EpisodeBaseSchema = z.object({
    publishStatus: z.enum(EpisodePublishStatus),
    wentLiveDate: z.date().optional(),
    publishedDate: z.date().optional(),
    title: z.string(),
    description: z.string(),
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
    showId: z.int(),
    seasonId: z.int(),
    index: z.number(),
    episodeIdentifier: z.string(),
    slug: z.string(),
    title: z.string(),
    publishStatus: z.union([z.enum(EpisodePublishStatus), z.string()]),
    earlyDeleteAvailable: z.boolean().optional().default(false),
    description: z.string(),
    sharingUrl: z.string(),
    duration: z.number(),
    backgroundImagePath: z.string().nullable().optional(),
    thumbnailLandscapePath: z.string().nullable().optional(),
    thumbnailPortraitPath: z.string().nullable().optional(),
    thumbnailSquarePath: z.string().nullable().optional(),
    wentLiveDate: ApiDateTimeSchema.nullable().optional(),
    publishedDate: ApiDateTimeSchema.nullable().optional(),
    scheduledDate: ApiDateTimeSchema.nullable().optional(),
    createdAt: ApiDateTimeSchema,
    updatedAt: ApiDateTimeSchema,
})
export type EpisodeRead = z.infer<typeof EpisodeReadSchema>

export const EpisodeReadViewSchema = z.object({
    id: z.int(),
    showId: z.int(),
    seasonId: z.int(),
    index: z.number(),
    episodeIdentifier: z.string(),
    slug: z.string(),
    title: z.string(),
    publishStatus: z.union([z.enum(EpisodePublishStatus), z.string()]),
    thumbnailPortraitPath: z.string().nullable().optional(),
})
export type EpisodeReadView = z.infer<typeof EpisodeReadViewSchema>
