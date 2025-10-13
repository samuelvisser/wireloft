import { z } from 'zod'
import { PodcastDownloadProfileReadSchema } from './podcast_download_profile'
import { SeriesDownloadProfileReadSchema } from './series_download_profile'

// Unified read view for a download profile coming from /download-profiles/as-view
export const DownloadProfileReadViewSchema = z.looseObject({
  id: z.int(),
  showId: z.int(),
  localMediaProfileId: z.int(),
  enableProfile: z.boolean(),
  type: z.enum(['podcast', 'series']),
  createdAt: z.iso.datetime().transform((s) => new Date(s)),
  updatedAt: z.iso.datetime().transform((s) => new Date(s)),

  // Added view fields
  showTitle: z.string(),
  localMediaProfilePreferredFormat: z.string(),

  // Concrete implementation payload (depends on `type`)
  downloadProfileImpl: z.union([PodcastDownloadProfileReadSchema, SeriesDownloadProfileReadSchema]),
})

export type DownloadProfileReadView = z.infer<typeof DownloadProfileReadViewSchema>
