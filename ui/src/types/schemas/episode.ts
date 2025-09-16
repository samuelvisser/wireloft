import {z} from 'zod';
import {EpisodePublishStatus} from "../episode";


const EpisodeBaseSchema = z.object({
    publish_status: z.enum(EpisodePublishStatus),
    went_live_date: z.date().optional(),
    published_date: z.date().optional(),
    redownloaded_date: z.date().optional(),
    title: z.string(),
    description: z.string(),
    downloaded_date: z.date().optional(),
})


export const EpisodeCreateSchema = EpisodeBaseSchema.extend({
    show_id: z.number(),
    index: z.number(),
    dw_id: z.string().optional(),
    slug: z.string(),
})
export type EpisodeCreate = z.infer<typeof EpisodeCreateSchema>


export const EpisodeReadSchema = EpisodeBaseSchema.extend({
    id: z.number(),
    show_id: z.number(),
    index: z.number(),
    uuid: z.string(),
    dw_id: z.string().optional(),
    slug: z.string(),
    created_at: z.date(),
    updated_at: z.date(),
})
export type EpisodeRead = z.infer<typeof EpisodeReadSchema>


export const EpisodeUpdateSchema = EpisodeBaseSchema.extend({
    dw_id: z.string().optional(),
})
export type EpisodeUpdate = z.infer<typeof EpisodeUpdateSchema>