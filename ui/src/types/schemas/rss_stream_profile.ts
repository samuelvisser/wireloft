import {z} from 'zod'
import {PreferredFormatReg} from "../local_media_profile";
import {RssDwVideoMethodReg} from "../stream_profile";

// ---------- Strict request (create/update) ----------
const RssStreamProfileBaseSchema = z.object({
    enableProfile: z.boolean().default(true),
    useDownloads: z.boolean().default(true),
    useDwStream: z.boolean().default(true),
    preferredFormat: z.enum(PreferredFormatReg.values),
    requireExactMatch: z.boolean().default(false),
    dwVideoMethod: z.enum(RssDwVideoMethodReg.values).default('stream_hls_download_m4a'),
    maxItems: z.int().nonnegative().default(0),
})

// On create, feedUrl is optional: leave it blank to have WireLoft generate
// one automatically once the profile (and its secret token) exists.
export const RssStreamProfileCreateSchema = RssStreamProfileBaseSchema.extend({
    showId: z.int(),
    feedUrl: z.string().optional(),
})
export type RssStreamProfileCreateIn = z.input<typeof RssStreamProfileCreateSchema>
export type RssStreamProfileCreateOut = z.output<typeof RssStreamProfileCreateSchema>

export const RssStreamProfileUpdateSchema = RssStreamProfileBaseSchema.extend({
    feedUrl: z.string().min(1),
})
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
    dwVideoMethod: z.union([z.enum(RssDwVideoMethodReg.values), z.string()]),
    maxItems: z.number(),
    feedUrl: z.string(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type RssStreamProfileRead = z.infer<typeof RssStreamProfileReadSchema>
