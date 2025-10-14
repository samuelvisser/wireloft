import {z} from 'zod'
import {RssStreamProfileReadSchema} from './rss_stream_profile'

export const StreamProfileReadSchema = z.looseObject({
    id: z.int(),
    showId: z.int(),
    enableProfile: z.boolean(),
    useDownloads: z.boolean(),
    useDwStream: z.boolean(),
    preferredFormat: z.string(),
    requireExactMatch: z.boolean(),
    type: z.enum(['rss']),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type StreamProfileRead = z.infer<typeof StreamProfileReadSchema>

// Unified read view from /stream-profiles/as-view
export const StreamProfileReadViewSchema = StreamProfileReadSchema.extend({
    showTitle: z.string(),
    showSlug: z.string(),
    // Concrete implementation payload
    streamProfileImpl: RssStreamProfileReadSchema,
})
export type StreamProfileReadView = z.infer<typeof StreamProfileReadViewSchema>
