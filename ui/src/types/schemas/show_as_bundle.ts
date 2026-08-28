import {ShowCreatePayloadSchema} from "./show";
import {PodcastDownloadProfileCreateSchema} from "./podcast_download_profile";
import {SeriesDownloadProfileCreateSchema} from "./series_download_profile";
import {LocalMediaProfileCreateSchema, LocalMediaProfileUpdateSchema} from "./local_media_profile";
import {RssStreamProfileCreateSchema} from "./rss_stream_profile";
import {z} from "zod";
import {SeasonDetachedSchema} from "./season";


export const PodcastDownloadProfileBundleSchema = PodcastDownloadProfileCreateSchema.omit({
    showId: true,
    localMediaProfileId: true,
}).extend({
    op: z.literal('podcast').default('podcast'),
})
export type PodcastDownloadProfileBundleIn = z.input<typeof PodcastDownloadProfileBundleSchema>
export type PodcastDownloadProfileBundleOut = z.output<typeof PodcastDownloadProfileBundleSchema>


export const SeriesDownloadProfileBundleSchema = SeriesDownloadProfileCreateSchema.omit({
    showId: true,
    localMediaProfileId: true,
}).safeExtend({
    op: z.literal('series').default('series'),
})
export type SeriesDownloadProfileBundleIn = z.input<typeof SeriesDownloadProfileBundleSchema>
export type SeriesDownloadProfileBundleOut = z.output<typeof SeriesDownloadProfileBundleSchema>


export const DownloadProfileUnifiedCreateSchema = z.discriminatedUnion('op', [
    PodcastDownloadProfileBundleSchema,
    SeriesDownloadProfileBundleSchema,
])
export type DownloadProfileUnifiedCreateIn = z.input<typeof DownloadProfileUnifiedCreateSchema>
export type DownloadProfileUnifiedCreateOut = z.output<typeof DownloadProfileUnifiedCreateSchema>


export const LocalMediaProfileCreateUnionSchema = LocalMediaProfileCreateSchema.extend({
    op: z.literal('create_new').default('create_new'),
})
export type LocalMediaProfileCreateUnionIn = z.input<typeof LocalMediaProfileCreateUnionSchema>
export type LocalMediaProfileCreateUnionOut = z.output<typeof LocalMediaProfileCreateUnionSchema>


export const LocalMediaProfileUpdateUnionSchema = LocalMediaProfileUpdateSchema.extend({
    op: z.literal('update_by_slug').default('update_by_slug'),
})
export type LocalMediaProfileUpdateUnionIn = z.input<typeof LocalMediaProfileUpdateUnionSchema>
export type LocalMediaProfileUpdateUnionOut = z.output<typeof LocalMediaProfileUpdateUnionSchema>


export const LocalMediaProfileUpsertSchema = z.discriminatedUnion('op', [
    LocalMediaProfileCreateUnionSchema,
    LocalMediaProfileUpdateUnionSchema,
])
export type LocalMediaProfileUpsertIn = z.input<typeof LocalMediaProfileUpsertSchema>
export type LocalMediaProfileUpsertOut = z.output<typeof LocalMediaProfileUpsertSchema>


export const RssStreamProfileBundleSchema = RssStreamProfileCreateSchema.omit({showId: true})
export type RssStreamProfileBundleIn = z.input<typeof RssStreamProfileBundleSchema>
export type RssStreamProfileBundleOut = z.output<typeof RssStreamProfileBundleSchema>


export const ShowCreateBundleSchema = z.object({
    show: ShowCreatePayloadSchema,
    seasons: z.array(SeasonDetachedSchema),
    localMediaProfile: LocalMediaProfileUpsertSchema.optional(),
    downloadProfile: DownloadProfileUnifiedCreateSchema.optional(),
    streamProfile: RssStreamProfileBundleSchema.optional(),
})
export type ShowCreateBundleIn = z.input<typeof ShowCreateBundleSchema>
export type ShowCreateBundleOut = z.output<typeof ShowCreateBundleSchema>
