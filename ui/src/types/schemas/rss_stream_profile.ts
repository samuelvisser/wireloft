import {z} from 'zod'
import {EpisodeTypeReg} from "../episode";
import {PreferredFormatReg} from "../local_media_profile";
import {RssVideoOutputModeReg} from "../stream_profile";
import {ApiDateTimeSchema} from "./datetime";

// ---------- Strict request (create/update) ----------
const RssStreamProfileBaseSchema = z.object({
    title: z.string().trim().min(1),
    enableProfile: z.boolean().default(true),
    useDownloads: z.boolean().default(true),
    useDwStream: z.boolean().default(true),
    preferredFormat: z.enum(PreferredFormatReg.values).refine(
        (value) => value !== 'format_hls',
        {message: 'HLS is a Local Media Profile download format, not a Stream Profile preferred format'},
    ),
    preferExactMatch: z.boolean().default(false),
    epIdTypeList: z.array(z.enum(EpisodeTypeReg.values)).default(['ep', 'aux']),
    videoOutputMode: z.enum(RssVideoOutputModeReg.values).nullable().default(null),
    streamLiveEpisodes: z.boolean().default(false),
    maxItems: z.int().nonnegative().default(100),
})

const validateVideoOutput = (
    value: {preferredFormat: string; videoOutputMode: string | null; streamLiveEpisodes: boolean},
    ctx: z.RefinementCtx,
) => {
    const audioOnly = value.preferredFormat === 'format_audio_only'

    if (audioOnly && value.videoOutputMode !== null) {
        ctx.addIssue({
            code: 'custom',
            path: ['videoOutputMode'],
            message: 'Audio-only Stream Profiles cannot have a video output mode',
        })
    }
    if (!audioOnly && value.videoOutputMode === null) {
        ctx.addIssue({
            code: 'custom',
            path: ['videoOutputMode'],
            message: 'Video Stream Profiles require a video output mode',
        })
    }

    if (!value.streamLiveEpisodes) return
    if (audioOnly) {
        ctx.addIssue({
            code: 'custom',
            path: ['streamLiveEpisodes'],
            message: 'Live episode streaming requires a video preferred format',
        })
        return
    }
    if (value.videoOutputMode === null || !['audio_hls', 'mp4_hls'].includes(value.videoOutputMode)) {
        ctx.addIssue({
            code: 'custom',
            path: ['streamLiveEpisodes'],
            message: 'Live episode streaming requires an HLS video output mode',
        })
    }
}

export const RssStreamProfileCreateSchema = RssStreamProfileBaseSchema.extend({
    showId: z.int(),
    feedUrl: z.string().optional(),
}).superRefine(validateVideoOutput)
export type RssStreamProfileCreateIn = z.input<typeof RssStreamProfileCreateSchema>
export type RssStreamProfileCreateOut = z.output<typeof RssStreamProfileCreateSchema>

export const RssStreamProfileUpdateSchema = RssStreamProfileBaseSchema.extend({
    feedUrl: z.string().min(1),
}).superRefine(validateVideoOutput)
export type RssStreamProfileUpdateIn = z.input<typeof RssStreamProfileUpdateSchema>
export type RssStreamProfileUpdateOut = z.output<typeof RssStreamProfileUpdateSchema>

export const RssStreamProfileReadSchema = z.looseObject({
    id: z.int(),
    showId: z.int(),
    enableProfile: z.boolean(),
    useDownloads: z.boolean(),
    useDwStream: z.boolean(),
    preferredFormat: z.union([z.enum(PreferredFormatReg.values), z.string()]),
    preferExactMatch: z.boolean(),
    epIdTypeList: z.array(z.union([z.enum(EpisodeTypeReg.values), z.string()])),
    videoOutputMode: z.union([z.enum(RssVideoOutputModeReg.values), z.string()]).nullable(),
    streamLiveEpisodes: z.boolean(),
    maxItems: z.number(),
    feedUrl: z.string(),
    effectiveTitle: z.string(),
    createdAt: ApiDateTimeSchema,
    updatedAt: ApiDateTimeSchema,
})
export type RssStreamProfileRead = z.infer<typeof RssStreamProfileReadSchema>
