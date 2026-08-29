import {z} from "zod";


// ---------- Strict request (create/update) ----------
const MovieBaseSchema = z.object({
    title: z.string(),
    description: z.string().nullable().optional(),
    downloadedDate: z.date().nullable().optional(),
    duration: z.number().default(0),
    backgroundImagePath: z.string().nullable().optional(),
    thumbnailLandscapePath: z.string().nullable().optional(),
    thumbnailPortraitPath: z.string().nullable().optional(),
    thumbnailSquarePath: z.string().nullable().optional(),
})


export const MovieCreateSchema = MovieBaseSchema.extend({
    dwId: z.string().optional(),
    slug: z.string(),
})
export type MovieCreateIn = z.input<typeof MovieCreateSchema>;
export type MovieCreateOut = z.output<typeof MovieCreateSchema>;


export const MovieUpdateSchema = MovieBaseSchema.extend({
})
export type MovieUpdateIn = z.input<typeof MovieUpdateSchema>;
export type MovieUpdateOut = z.output<typeof MovieUpdateSchema>;


// ------------ Lenient response (read) ------------
export const MovieReadSchema = z.looseObject({
    id: z.int(),
    uuid: z.string(),
    dwId: z.string().optional(),
    slug: z.string(),
    title: z.string(),
    description: z.string().nullable().optional(),
    downloadedDate: z.iso.datetime().transform((s) => new Date(s)).nullable().optional(),
    duration: z.number(),
    backgroundImagePath: z.string().nullable(),
    thumbnailLandscapePath: z.string().nullable(),
    thumbnailPortraitPath: z.string().nullable(),
    thumbnailSquarePath: z.string().nullable(),
    sharingUrl: z.string().nullable(),
    authorName: z.string().nullable(),
    matureRating: z.string().nullable(),
    isDownloadable: z.boolean().nullable(),
    trailerSlug: z.string().nullable(),
    trailerTitle: z.string().nullable(),
    trailerSharingUrl: z.string().nullable(),
    trailerThumbnailPath: z.string().nullable(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type MovieRead = z.infer<typeof MovieReadSchema>;
