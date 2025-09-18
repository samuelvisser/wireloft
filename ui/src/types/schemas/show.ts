import {z} from "zod";
import {EpisodeIdentifier, ShowType} from "../show";


// ---------- Strict request (create/update) ----------
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


export const ShowUpdateSchema = ShowBaseSchema.extend({
})
export type ShowUpdate = z.infer<typeof ShowUpdateSchema>;


// ------------ Lenient response (read) ------------
export const ShowReadSchema = z.looseObject({
    id: z.number(),
    uuid: z.string(),
    dwId: z.string(),
    slug: z.string(),
    type: z.union([z.enum(ShowType), z.string()]),
    episodeIdentifier: z.union([z.enum(EpisodeIdentifier), z.string()]),
    authorSlug: z.string(),
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
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type ShowRead = z.infer<typeof ShowReadSchema>;