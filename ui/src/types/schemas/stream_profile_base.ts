import {z} from 'zod'
import {EpisodeTypeReg} from '../episode'
import {ApiDateTimeSchema} from './datetime'
import {RssStreamProfileReadSchema} from './rss_stream_profile'

export const StreamProfileReadSchema = z.looseObject({
    id: z.int(),
    showId: z.int(),
    enableProfile: z.boolean(),
    useDownloads: z.boolean(),
    useDwStream: z.boolean(),
    preferredFormat: z.string(),
    requireExactMatch: z.boolean(),
    epIdTypeList: z.array(z.union([z.enum(EpisodeTypeReg.values), z.string()])),
    type: z.enum(['rss']),
    createdAt: ApiDateTimeSchema,
    updatedAt: ApiDateTimeSchema,
})
export type StreamProfileRead = z.infer<typeof StreamProfileReadSchema>

// Unified read view from /stream-profiles/as-view
export const StreamProfileReadViewSchema = StreamProfileReadSchema.extend({
    showTitle: z.string(),
    showSlug: z.string(),
    streamProfileImpl: RssStreamProfileReadSchema,
})
export type StreamProfileReadView = z.infer<typeof StreamProfileReadViewSchema>
