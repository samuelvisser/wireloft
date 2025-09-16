import {z} from "zod";
import {EpisodeIdentifier, ShowType} from "../show";


const ShowBaseSchema = z.object({
    title: z.string(),
    description: z.string(),
    url: z.string(),
    authorName: z.string(),
    authorHeadshotPath: z.string().optional(),
    backgroundImagePath: z.string().optional(),
    logoImagePath: z.string().optional(),
    thumbnailLandscapePath: z.string().optional(),
    thumbnailPortraitPath: z.string().optional(),
    thumbnailSquarePath: z.string().optional(),
})


export const ShowCreateSchema = ShowBaseSchema.extend({
    dwId: z.string(),
    slug: z.string(),
    type: z.enum(["series", "movie"]),
    episodeIdentifier: z.enum(EpisodeIdentifier),
    authorSlug: z.string(),
})
export type ShowCreate = z.infer<typeof ShowCreateSchema>;


export const ShowReadSchema = ShowBaseSchema.extend({
    id: z.number(),
    uuid: z.string(),
    dwId: z.string(),
    slug: z.string(),
    type: z.enum(ShowType),
    episodeIdentifier: z.enum(EpisodeIdentifier),
    authorSlug: z.string(),
    createdAt: z.date(),
    updatedAt: z.date(),
})
export type ShowRead = z.infer<typeof ShowReadSchema>;


export const ShowUpdateSchema = ShowBaseSchema.extend({
})
export type ShowUpdate = z.infer<typeof ShowUpdateSchema>;