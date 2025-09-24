import {ShowCreatePayloadSchema} from "./show";
import {DownloadProfilePodcastCreateSchema} from "./download_profile_podcast";
import {DownloadProfileSeriesCreateSchema} from "./download_profile_series";
import {MediaProfileCreateSchema, MediaProfileUpdateSchema} from "./media_profile";
import {z} from "zod";


export const DownloadProfilePodcastWithProfilesSchema = DownloadProfilePodcastCreateSchema.omit({
    showId: true,
    mediaProfileId: true,
}).extend({
    op: z.literal('podcast').default('podcast'),
})
export type DownloadProfilePodcastWithProfilesIn = z.input<typeof DownloadProfilePodcastWithProfilesSchema>
export type DownloadProfilePodcastWithProfilesOut = z.output<typeof DownloadProfilePodcastWithProfilesSchema>


export const DownloadProfileSeriesWithProfilesSchema = DownloadProfileSeriesCreateSchema.omit({
    showId: true,
    mediaProfileId: true,
}).safeExtend({
    op: z.literal('series').default('series'),
})
export type DownloadProfileSeriesWithProfilesIn = z.input<typeof DownloadProfileSeriesWithProfilesSchema>
export type DownloadProfileSeriesWithProfilesOut = z.output<typeof DownloadProfileSeriesWithProfilesSchema>


export const DownloadProfileUnifiedCreateSchema = z.discriminatedUnion('op', [
    DownloadProfilePodcastWithProfilesSchema,
    DownloadProfileSeriesWithProfilesSchema,
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


export const ShowCreateWithProfilesSchema = z.object({
    show: ShowCreatePayloadSchema,
    mediaProfile: MediaProfileUpsertSchema,
    downloadProfile: DownloadProfileUnifiedCreateSchema,
})
export type ShowCreateWithProfilesIn = z.input<typeof ShowCreateWithProfilesSchema>
export type ShowCreateWithProfilesOut = z.output<typeof ShowCreateWithProfilesSchema>
