import {ShowCreatePayloadSchema} from "./show";
import {DownloadProfilePodcastCreateSchema} from "./download_profile_podcast";
import {DownloadProfileSeriesCreateSchema} from "./download_profile_series";
import {MediaProfileCreateSchema, MediaProfileUpdateSchema} from "./media_profile";
import {z} from "zod";
import {SeasonDetachedSchema} from "./season";


export const DownloadProfilePodcastBundleSchema = DownloadProfilePodcastCreateSchema.omit({
    showId: true,
    mediaProfileId: true,
}).extend({
    op: z.literal('podcast').default('podcast'),
})
export type DownloadProfilePodcastBundleIn = z.input<typeof DownloadProfilePodcastBundleSchema>
export type DownloadProfilePodcastBundleOut = z.output<typeof DownloadProfilePodcastBundleSchema>


export const DownloadProfileSeriesBundleSchema = DownloadProfileSeriesCreateSchema.omit({
    showId: true,
    mediaProfileId: true,
}).safeExtend({
    op: z.literal('series').default('series'),
})
export type DownloadProfileSeriesBundleIn = z.input<typeof DownloadProfileSeriesBundleSchema>
export type DownloadProfileSeriesBundleOut = z.output<typeof DownloadProfileSeriesBundleSchema>


export const DownloadProfileUnifiedCreateSchema = z.discriminatedUnion('op', [
    DownloadProfilePodcastBundleSchema,
    DownloadProfileSeriesBundleSchema,
])
export type DownloadProfileUnifiedCreateIn = z.input<typeof DownloadProfileUnifiedCreateSchema>
export type DownloadProfileUnifiedCreateOut = z.output<typeof DownloadProfileUnifiedCreateSchema>


export const MediaProfileCreateUnionSchema = MediaProfileCreateSchema.extend({
    op: z.literal('create_new').default('create_new'),
})
export type MediaProfileCreateUnionIn = z.input<typeof MediaProfileCreateUnionSchema>
export type MediaProfileCreateUnionOut = z.output<typeof MediaProfileCreateUnionSchema>


export const MediaProfileUpdateUnionSchema = MediaProfileUpdateSchema.extend({
    op: z.literal('update_by_slug').default('update_by_slug'),
})
export type MediaProfileUpdateUnionIn = z.input<typeof MediaProfileUpdateUnionSchema>
export type MediaProfileUpdateUnionOut = z.output<typeof MediaProfileUpdateUnionSchema>


export const MediaProfileUpsertSchema = z.discriminatedUnion('op', [
    MediaProfileCreateUnionSchema,
    MediaProfileUpdateUnionSchema,
])
export type MediaProfileUpsertIn = z.input<typeof MediaProfileUpsertSchema>
export type MediaProfileUpsertOut = z.output<typeof MediaProfileUpsertSchema>


export const ShowCreateBundleSchema = z.object({
    show: ShowCreatePayloadSchema,
    mediaProfile: MediaProfileUpsertSchema,
    downloadProfile: DownloadProfileUnifiedCreateSchema,
    seasons: z.array(SeasonDetachedSchema),
})
export type ShowCreateBundleIn = z.input<typeof ShowCreateBundleSchema>
export type ShowCreateBundleOut = z.output<typeof ShowCreateBundleSchema>
