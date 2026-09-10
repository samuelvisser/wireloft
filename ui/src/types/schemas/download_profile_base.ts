import {z} from 'zod'
import {EpisodeTypeReg} from "../episode";
import {ApiDateTimeSchema} from "./datetime";


export const DownloadProfileStorageModeSchema = z.enum(['system', 'direct', 'temporary'])
export type DownloadProfileStorageMode = z.infer<typeof DownloadProfileStorageModeSchema>


// ---------- Strict request (create/update) ----------
export const DownloadProfileSchemaRequest = z.object({
    enableProfile: z.boolean().default(true),
    downloadMode: DownloadProfileStorageModeSchema.default('system'),
    epIdTypeList: z.array(z.enum(EpisodeTypeReg.values)).default([]),
})

export const DownloadProfileCreateSchema = DownloadProfileSchemaRequest.extend({
    showId: z.int(),
    localMediaProfileId: z.int(),
})

export const DownloadProfileUpdateSchema = DownloadProfileSchemaRequest.extend({
    localMediaProfileId: z.int(),
})


// ------------ Lenient response (read) ------------
export const DownloadProfileSchemaResponse = z.looseObject({
    id: z.int(),
    showId: z.int(),
    localMediaProfileId: z.int(),
    enableProfile: z.boolean(),
    downloadMode: DownloadProfileStorageModeSchema.default('system'),
    epIdTypeList: z.array(z.union([z.enum(EpisodeTypeReg.values), z.string()])),
    createdAt: ApiDateTimeSchema,
    updatedAt: ApiDateTimeSchema,
})

export const DownloadProfileReadSchema = DownloadProfileSchemaResponse.safeExtend({
    type: z.enum(['podcast', 'series']),
})
export type DownloadProfileRead = z.infer<typeof DownloadProfileReadSchema>