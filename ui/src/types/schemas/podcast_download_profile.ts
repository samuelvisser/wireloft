import {z} from 'zod';
import {
    DownloadProfileSchemaRequest,
    DownloadProfileCreateSchema,
    DownloadProfileUpdateSchema,
    DownloadProfileSchemaResponse
} from "./download_profile_base";


// ---------- Strict request (create/update) ----------
const PodcastDownloadProfileBaseSchema = DownloadProfileSchemaRequest.extend({
    downloadWithCountdown: z.boolean().default(false),
    redownloadFinal: z.boolean().default(true),
    downloadDaysInPast: z.int().min(0).default(180),
    deleteOlderEpisodes: z.boolean().default(true),
})

export const PodcastDownloadProfileCreateSchema = PodcastDownloadProfileBaseSchema.extend(
    DownloadProfileCreateSchema.shape
)
export type PodcastDownloadProfileCreateIn = z.input<typeof PodcastDownloadProfileCreateSchema>
export type PodcastDownloadProfileCreateOut = z.output<typeof PodcastDownloadProfileCreateSchema>


export const PodcastDownloadProfileUpdateSchema = PodcastDownloadProfileBaseSchema.extend(
    DownloadProfileUpdateSchema.shape
)
export type PodcastDownloadProfileUpdateIn = z.input<typeof PodcastDownloadProfileUpdateSchema>
export type PodcastDownloadProfileUpdateOut = z.output<typeof PodcastDownloadProfileUpdateSchema>


// ------------ Lenient response (read) ------------
export const PodcastDownloadProfileReadSchema = DownloadProfileSchemaResponse.safeExtend({
    type: z.literal('podcast'),
    downloadWithCountdown: z.boolean(),
    redownloadFinal: z.boolean(),
    downloadDaysInPast: z.int(),
    deleteOlderEpisodes: z.boolean(),
})
export type PodcastDownloadProfileRead = z.infer<typeof PodcastDownloadProfileReadSchema>