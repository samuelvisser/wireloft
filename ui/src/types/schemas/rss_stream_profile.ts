import {z} from 'zod'
import {PreferredFormatReg} from "../local_media_profile";

// ---------- Strict request (create/update) ----------
const RssStreamProfileBaseSchema = z.object({
    enableProfile: z.boolean().default(true),
    useDownloads: z.boolean().default(true),
    useDwStream: z.boolean().default(true),
    preferredFormat: z.enum(PreferredFormatReg.values),
    requireExactMatch: z.boolean().default(true),
    feedUrl: z.string().min(1),
})

export const RssStreamProfileCreateSchema = RssStreamProfileBaseSchema.extend({
    showId: z.int(),
})
export type RssStreamProfileCreateIn = z.input<typeof RssStreamProfileCreateSchema>
export type RssStreamProfileCreateOut = z.output<typeof RssStreamProfileCreateSchema>

export const RssStreamProfileUpdateSchema = RssStreamProfileBaseSchema.extend({})
export type RssStreamProfileUpdateIn = z.input<typeof RssStreamProfileUpdateSchema>
export type RssStreamProfileUpdateOut = z.output<typeof RssStreamProfileUpdateSchema>

// ------------ Lenient response (read) ------------
export const RssStreamProfileReadSchema = z.looseObject({
    id: z.int(),
    showId: z.int(),
    enableProfile: z.boolean(),
    useDownloads: z.boolean(),
    useDwStream: z.boolean(),
    preferredFormat: z.union([z.enum(PreferredFormatReg.values), z.string()]),
    requireExactMatch: z.boolean(),
    feedUrl: z.string(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type RssStreamProfileRead = z.infer<typeof RssStreamProfileReadSchema>
