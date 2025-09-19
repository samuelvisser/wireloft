import {z} from "zod";
import {EpisodeIdentifier, ShowType} from "../show";

function ensureProtocol(input: string): string {
    let v = (input ?? '').trim()
    if (!v) return v
    // If the string doesn't start with a URL scheme, prepend https://
    if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(v)) {
        v = 'https://' + v
    }
    return v
}

// ---------- Strict request (create/update) ----------
const ShowBaseSchema = z.object({
    title: z.string(),
    description: z.string(),

    // Validate URL
    url: z
        .string()
        .min(1, {message: 'URL is required'})
        .transform(ensureProtocol)
        .refine((s) => {
            try {
                const u = new URL(s)
                const host = u.hostname.toLowerCase()
                return host === 'dailywire.com' || host === 'www.dailywire.com'
            } catch {
                return false
            }
        }, {message: 'URL must be on dailywire.com'})
        .refine((s) => {
            try {
                const u = new URL(s)
                return u.pathname.startsWith('/show/')
            } catch {
                return false
            }
        }, {message: 'URL must include /show/ in the path'})
        .refine((s) => {
            try {
                const u = new URL(s)
                const slug = u.pathname.slice('/show/'.length).split('/')[0]
                return !!slug
            } catch {
                return false
            }
        }, {message: 'URL must include a show name after /show/ (e.g., the-ben-shapiro-show)'}),

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
    type: z.enum(ShowType),
    episodeIdentifier: z.enum(EpisodeIdentifier),
    authorSlug: z.string(),
})
export type ShowCreate = z.infer<typeof ShowCreateSchema>;


export const ShowUpdateSchema = ShowBaseSchema.extend({})
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