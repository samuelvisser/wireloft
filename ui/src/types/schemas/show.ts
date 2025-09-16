import {z} from "zod";
import {EpisodeIdentifier, ShowType} from "../show";


const ShowBaseSchema = z.object({
    title: z.string(),
    description: z.string(),
    url: z.string(),
    author_name: z.string(),
    author_headshot_path: z.string().optional(),
    background_image_path: z.string().optional(),
    logo_image_path: z.string().optional(),
    thumbnail_landscape_path: z.string().optional(),
    thumbnail_portrait_path: z.string().optional(),
    thumbnail_square_path: z.string().optional(),
})


export const ShowCreateSchema = ShowBaseSchema.extend({
    dw_id: z.string(),
    slug: z.string(),
    type: z.enum(["series", "movie"]),
    episode_identifier: z.enum(EpisodeIdentifier),
    author_slug: z.string(),
})
export type ShowCreate = z.infer<typeof ShowCreateSchema>;


export const ShowReadSchema = ShowBaseSchema.extend({
    id: z.number(),
    uuid: z.string(),
    dw_id: z.string(),
    slug: z.string(),
    type: z.enum(ShowType),
    episode_identifier: z.enum(EpisodeIdentifier),
    author_slug: z.string(),
    created_at: z.date(),
    updated_at: z.date(),
})
export type ShowRead = z.infer<typeof ShowReadSchema>;


export const ShowUpdateSchema = ShowBaseSchema.extend({
})
export type ShowUpdate = z.infer<typeof ShowUpdateSchema>;