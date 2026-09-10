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
    downloadEpisodeCount: z.int().min(0).default(0),
    downloadStartingFrom: z.iso.date().nullable().default(null),
    deleteOlderEpisodes: z.boolean().default(true),
})

export const PodcastDownloadProfileCreateSchema = PodcastDownloadProfileBaseSchema.extend(
    DownloadProfileCreateSchema.shape
).superRefine((value, ctx) => {
    if (value.downloadDaysInPast > 0 && value.downloadEpisodeCount > 0) {
        ctx.addIssue({
            code: 'custom',
            path: ['downloadDaysInPast'],
            message: 'Choose either a date limit or an episode-count limit, not both',
        })
    }
    if (value.downloadStartingFrom !== null && (value.downloadDaysInPast > 0 || value.downloadEpisodeCount > 0)) {
        ctx.addIssue({
            code: 'custom',
            path: ['downloadStartingFrom'],
            message: 'Download starting from can only be used when Limit by is set to No limits',
        })
    }
})
export type PodcastDownloadProfileCreateIn = z.input<typeof PodcastDownloadProfileCreateSchema>
export type PodcastDownloadProfileCreateOut = z.output<typeof PodcastDownloadProfileCreateSchema>


export const PodcastDownloadProfileUpdateSchema = PodcastDownloadProfileBaseSchema.extend(
    DownloadProfileUpdateSchema.shape
).superRefine((value, ctx) => {
    if (value.downloadDaysInPast > 0 && value.downloadEpisodeCount > 0) {
        ctx.addIssue({
            code: 'custom',
            path: ['downloadDaysInPast'],
            message: 'Choose either a date limit or an episode-count limit, not both',
        })
    }
    if (value.downloadStartingFrom !== null && (value.downloadDaysInPast > 0 || value.downloadEpisodeCount > 0)) {
        ctx.addIssue({
            code: 'custom',
            path: ['downloadStartingFrom'],
            message: 'Download starting from can only be used when Limit by is set to No limits',
        })
    }
})
export type PodcastDownloadProfileUpdateIn = z.input<typeof PodcastDownloadProfileUpdateSchema>
export type PodcastDownloadProfileUpdateOut = z.output<typeof PodcastDownloadProfileUpdateSchema>


// ------------ Lenient response (read) ------------
export const PodcastDownloadProfileReadSchema = DownloadProfileSchemaResponse.safeExtend({
    type: z.literal('podcast'),
    downloadWithCountdown: z.boolean(),
    redownloadFinal: z.boolean(),
    downloadDaysInPast: z.int(),
    downloadEpisodeCount: z.int(),
    downloadStartingFrom: z.iso.date().nullable(),
    deleteOlderEpisodes: z.boolean(),
})
export type PodcastDownloadProfileRead = z.infer<typeof PodcastDownloadProfileReadSchema>
