import {z} from 'zod'
import {EpisodeTypeReg} from "../episode";
import {PreferredFormatReg} from "../local_media_profile";
import {RssVideoOutputModeReg} from "../stream_profile";
import {ApiDateTimeSchema} from "./datetime";

// ---------- Strict request (create/update) ----------
const RssStreamProfileBaseSchema = z.object({
    enableProfile: z.boolean().default(true),
    useDownloads: z.boolean().default(true),
    useDwStream: z.boolean().default(true),
    preferredFormat: z.enum(PreferredFormatReg.values).refine(
        (value) => value !== 'format_hls',
        {message: 'HLS is a Local Media Profile download format, not a Stream Profile preferred format'},
    ),
    requireExactMatch: z.boolean().default(false),
    epIdTypeList: z.array(z.enum(EpisodeTypeReg.values)).default(['ep', 'aux']),
    videoOutputMode: z.enum(RssVideoOutputModeReg.values).default('audio_hls'),
    streamLiveEpisodes: z.boolean().default(false),
    maxItems: z.int().nonnegative().default(0),
})

const validateLiveVideoOutput = (
    value: {preferredFormat: string; videoOutputMode: string; streamLiveEpisodes: boolean},
    ctx: z.RefinementCtx,
) => {
    if (!value.streamLiveEpisodes) return
    if (!['audio_hls', 'mp4_hls'].includes(value.videoOutputMode)) {
        ctx.addIssue({
            code: 'custom',
            path: ['streamLiveEpisodes'],
            message: 'Live episode streaming requires an HLS video output mode',
        })
    }
    if (value.preferredFormat === 'format_audio_only') {
        ctx.addIssue({
            code: 'custom',
            path: ['streamLiveEpisodes'],
            message: 'Live episode streaming requires a video preferred format',
        })
    }
}

export const RssStreamProfileCreateSchema = RssStreamProfileBaseSchema.extend({
    showId: z.int(),
    feedUrl: z.string().optional(),
}).superRefine(validateLiveVideoOutput)
export type RssStreamProfileCreateIn = z.input<typeof RssStreamProfileCreateSchema>
export type RssStreamProfileCreateOut = z.output<typeof RssStreamProfileCreateSchema>

export const RssStreamProfileUpdateSchema = RssStreamProfileBaseSchema.extend({
    feedUrl: z.string().min(1),
}).superRefine(validateLiveVideoOutput)
export type RssStreamProfileUpdateIn = z.input<typeof RssStreamProfileUpdateSchema>
export type RssStreamProfileUpdateOut = z.output<typeof RssStreamProfileUpdateSchema>

export const RssStreamProfileReadSchema = z.looseObject({
    id: z.int(),
    showId: z.int(),
    enableProfile: z.boolean(),
    useDownloads: z.boolean(),
    useDwStream: z.boolean(),
    preferredFormat: z.union([z.enum(PreferredFormatReg.values), z.string()]),
    requireExactMatch: z.boolean(),
    epIdTypeList: z.array(z.union([z.enum(EpisodeTypeReg.values), z.string()])),
    videoOutputMode: z.union([z.enum(RssVideoOutputModeReg.values), z.string()]),
    streamLiveEpisodes: z.boolean(),
    maxItems: z.number(),
    feedUrl: z.string(),
    createdAt: ApiDateTimeSchema,
    updatedAt: ApiDateTimeSchema,
})
export type RssStreamProfileRead = z.infer<typeof RssStreamProfileReadSchema>
