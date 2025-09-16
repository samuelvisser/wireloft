import {z} from 'zod';


const DownloadProfilePodcastBaseSchema = z.object({
    mediaProfileId: z.number().optional(),
    enableProfile: z.boolean(),
    downloadWithCountdown: z.boolean(),
    redownloadFinal: z.boolean(),
    downloadDaysInPast: z.number().min(0),
    deleteOlderEpisodes: z.boolean(),
})

export const DownloadProfilePodcastCreateSchema = DownloadProfilePodcastBaseSchema.extend({
    showId: z.number(),
})
export type DownloadProfilePodcastCreate = z.infer<typeof DownloadProfilePodcastCreateSchema>


export const DownloadProfilePodcastReadSchema = DownloadProfilePodcastBaseSchema.extend({
    id: z.number(),
    showId: z.number(),
    createdAt: z.date(),
    updatedAt: z.date(),
})
export type DownloadProfilePodcastRead = z.infer<typeof DownloadProfilePodcastReadSchema>


export const DownloadProfilePodcastUpdateSchema = DownloadProfilePodcastBaseSchema.extend({
})
export type DownloadProfilePodcastUpdate = z.infer<typeof DownloadProfilePodcastUpdateSchema>
