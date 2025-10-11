import {z} from 'zod';


// ---------- Strict request (create/update) ----------
const PodcastDownloadProfileBaseSchema = z.object({
    localMediaProfileId: z.int(),
    enableProfile: z.boolean().default(true),
    downloadWithCountdown: z.boolean().default(false),
    redownloadFinal: z.boolean().default(true),
    downloadDaysInPast: z.int().min(0).default(180),
    deleteOlderEpisodes: z.boolean().default(true),
})

export const PodcastDownloadProfileCreateSchema = PodcastDownloadProfileBaseSchema.extend({
    showId: z.int(),
})
export type PodcastDownloadProfileCreateIn = z.input<typeof PodcastDownloadProfileCreateSchema>
export type PodcastDownloadProfileCreateOut = z.output<typeof PodcastDownloadProfileCreateSchema>


export const PodcastDownloadProfileUpdateSchema = PodcastDownloadProfileBaseSchema.extend({
})
export type PodcastDownloadProfileUpdateIn = z.input<typeof PodcastDownloadProfileUpdateSchema>
export type PodcastDownloadProfileUpdateOut = z.output<typeof PodcastDownloadProfileUpdateSchema>


// ------------ Lenient response (read) ------------
export const PodcastDownloadProfileReadSchema = z.looseObject({
    id: z.int(),
    showId: z.int(),
    localMediaProfileId: z.int().optional(),
    enableProfile: z.boolean(),
    downloadWithCountdown: z.boolean(),
    redownloadFinal: z.boolean(),
    downloadDaysInPast: z.int(),
    deleteOlderEpisodes: z.boolean(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type PodcastDownloadProfileRead = z.infer<typeof PodcastDownloadProfileReadSchema>