import {ShowCreatePayloadSchema} from "./show";
import {DownloadProfilePodcastCreateSchema} from "./download_profile_podcast";
import {DownloadProfileSeriesCreateSchema} from "./download_profile_series";
import {MediaProfileCreateSchema, MediaProfileUpdateSchema} from "./media_profile";
import {z} from "zod";

export const MediaProfileCreateUnionSchema = MediaProfileCreateSchema.extend({
    op: z.literal('create_new'),
})
export type MediaProfileCreateUnionIn = z.input<typeof MediaProfileCreateUnionSchema>
export type MediaProfileCreateUnionOut = z.output<typeof MediaProfileCreateUnionSchema>


export const MediaProfileUpdateUnionSchema = MediaProfileUpdateSchema.extend({
    op: z.literal('update_by_slug'),
})
export type MediaProfileUpdateUnionIn = z.input<typeof MediaProfileUpdateUnionSchema>
export type MediaProfileUpdateUnionOut = z.output<typeof MediaProfileUpdateUnionSchema>


export const MediaProfileUpsertSchema = z.discriminatedUnion('op', [
  MediaProfileCreateUnionSchema,
  MediaProfileUpdateUnionSchema,
])
export type MediaProfileUpsertIn = z.input<typeof MediaProfileUpsertSchema>
// export type MediaProfileUpsertUnionIn = MediaProfileCreateUnionIn | MediaProfileUpdateUnionIn
export type MediaProfileUpsertOut = z.output<typeof MediaProfileUpsertSchema>
// export type MediaProfileUpsertUnionOut = MediaProfileCreateUnionOut | MediaProfileUpdateUnionOut


export const ShowCreateWithProfilesSchema = z.object({
    show: ShowCreatePayloadSchema,
    mediaProfile: MediaProfileUpsertSchema,
    downloadProfile: z.discriminatedUnion('op', [
        DownloadProfilePodcastCreateSchema.extend({
            op: z.literal('podcast'),
        }),
        DownloadProfileSeriesCreateSchema.extend({
            op: z.literal('series'),
        })
    ]),
})
export type ShowCreateWithProfilesIn = z.input<typeof ShowCreateWithProfilesSchema>
export type ShowCreateWithProfilesOut = z.output<typeof ShowCreateWithProfilesSchema>
