import {z} from 'zod';


// ---------- Strict request (create/update) ----------
const DownloadProfilePodcastBaseSchema = z.object({
    mediaProfileId: z.int(),
    enableProfile: z.boolean().default(true),
    downloadWithCountdown: z.boolean().default(false),
    redownloadFinal: z.boolean().default(true),
    downloadDaysInPast: z.int().min(0).default(180),
    deleteOlderEpisodes: z.boolean().default(true),
})

export const DownloadProfilePodcastCreateSchema = DownloadProfilePodcastBaseSchema.extend({
    showId: z.int(),
})
export type DownloadProfilePodcastCreateIn = z.input<typeof DownloadProfilePodcastCreateSchema>
export type DownloadProfilePodcastCreateOut = z.output<typeof DownloadProfilePodcastCreateSchema>


export const DownloadProfilePodcastUpdateSchema = DownloadProfilePodcastBaseSchema.extend({
})
export type DownloadProfilePodcastUpdateIn = z.input<typeof DownloadProfilePodcastUpdateSchema>
export type DownloadProfilePodcastUpdateOut = z.output<typeof DownloadProfilePodcastUpdateSchema>


// ------------ Lenient response (read) ------------
export const DownloadProfilePodcastReadSchema = z.looseObject({
    id: z.int(),
    showId: z.int(),
    mediaProfileId: z.int().optional(),
    enableProfile: z.boolean(),
    downloadWithCountdown: z.boolean(),
    redownloadFinal: z.boolean(),
    downloadDaysInPast: z.int(),
    deleteOlderEpisodes: z.boolean(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type DownloadProfilePodcastRead = z.infer<typeof DownloadProfilePodcastReadSchema>