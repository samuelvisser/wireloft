import {z} from 'zod';


const DownloadProfilePodcastBaseSchema = z.object({
    media_profile_id: z.number().optional(),
    enable_profile: z.boolean(),
    download_with_countdown: z.boolean(),
    redownload_final: z.boolean(),
    download_days_in_past: z.number().min(0),
    delete_older_episodes: z.boolean(),
})

export const DownloadProfilePodcastCreateSchema = DownloadProfilePodcastBaseSchema.extend({
    show_id: z.number(),
})
export type DownloadProfilePodcastCreate = z.infer<typeof DownloadProfilePodcastCreateSchema>


export const DownloadProfilePodcastReadSchema = DownloadProfilePodcastBaseSchema.extend({
    id: z.number(),
    show_id: z.number(),
    created_at: z.date(),
    updated_at: z.date(),
})
export type DownloadProfilePodcastRead = z.infer<typeof DownloadProfilePodcastReadSchema>


export const DownloadProfilePodcastUpdateSchema = DownloadProfilePodcastBaseSchema.extend({
})
export type DownloadProfilePodcastUpdate = z.infer<typeof DownloadProfilePodcastUpdateSchema>
