import {z} from 'zod';
import {EpisodePublishStatus} from "../episode";


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
    showId: z.number(),
    index: z.number(),
    dwId: z.string().optional(),
    slug: z.string(),
})
export type EpisodeCreate = z.infer<typeof EpisodeCreateSchema>


export const EpisodeReadSchema = EpisodeBaseSchema.extend({
    id: z.number(),
    showId: z.number(),
    index: z.number(),
    uuid: z.string(),
    dwId: z.string().optional(),
    slug: z.string(),
    createdAt: z.date(),
    updatedAt: z.date(),
})
export type EpisodeRead = z.infer<typeof EpisodeReadSchema>


export const EpisodeUpdateSchema = EpisodeBaseSchema.extend({
    dwId: z.string().optional(),
})
export type EpisodeUpdate = z.infer<typeof EpisodeUpdateSchema>