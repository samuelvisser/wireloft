import {z} from 'zod'
import {PodcastDownloadProfileReadSchema} from './podcast_download_profile'
import {SeriesDownloadProfileReadSchema} from './series_download_profile'

export const DownloadProfileReadSchema = z.looseObject({
    id: z.int(),
    showId: z.int(),
    localMediaProfileId: z.int(),
    enableProfile: z.boolean(),
    type: z.enum(['podcast', 'series']),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type DownloadProfileRead = z.infer<typeof DownloadProfileReadSchema>

// Unified read view for a download profile coming from /download-profiles/as-view
export const DownloadProfileReadViewSchema = DownloadProfileReadSchema.extend({
    // External table fields
    showTitle: z.string(),
    showSlug: z.string(),
    localMediaProfilePreferredFormat: z.string(),

    // Concrete implementation payload (depends on `type`)
    downloadProfileImpl: z.discriminatedUnion('type', [
        PodcastDownloadProfileReadSchema,
        SeriesDownloadProfileReadSchema,
    ]),
})
export type DownloadProfileReadView = z.infer<typeof DownloadProfileReadViewSchema>