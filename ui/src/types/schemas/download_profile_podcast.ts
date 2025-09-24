import {z} from 'zod';


// ---------- Strict request (create/update) ----------
const DownloadProfilePodcastBaseSchema = z.object({
    mediaProfileId: z.number(),
    enableProfile: z.boolean().default(true),
    downloadWithCountdown: z.boolean().default(false),
    redownloadFinal: z.boolean().default(true),
    downloadDaysInPast: z.number().min(0).default(180),
    deleteOlderEpisodes: z.boolean().default(true),
})

export const DownloadProfilePodcastCreateSchema = DownloadProfilePodcastBaseSchema.extend({
    showId: z.number(),
})
export type DownloadProfilePodcastCreateIn = z.input<typeof DownloadProfilePodcastCreateSchema>
export type DownloadProfilePodcastCreateOut = z.output<typeof DownloadProfilePodcastCreateSchema>


export const DownloadProfilePodcastUpdateSchema = DownloadProfilePodcastBaseSchema.extend({
})
export type DownloadProfilePodcastUpdateIn = z.input<typeof DownloadProfilePodcastUpdateSchema>
export type DownloadProfilePodcastUpdateOut = z.output<typeof DownloadProfilePodcastUpdateSchema>


// ------------ Lenient response (read) ------------
export const DownloadProfilePodcastReadSchema = z.looseObject({
    id: z.number(),
    showId: z.number(),
    mediaProfileId: z.number().optional(),
    enableProfile: z.boolean(),
    downloadWithCountdown: z.boolean(),
    redownloadFinal: z.boolean(),
    downloadDaysInPast: z.number(),
    deleteOlderEpisodes: z.boolean(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type DownloadProfilePodcastRead = z.infer<typeof DownloadProfilePodcastReadSchema>