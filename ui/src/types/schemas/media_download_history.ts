import {z} from 'zod'
import {ApiDateTimeStringSchema} from './datetime'

export const MediaDownloadHistoryEntryReadSchema = z.looseObject({
  key: z.string(),
  status: z.string(),
  activity: z.string(),
  occurredAt: ApiDateTimeStringSchema.nullable(),
  error: z.string().nullable(),
})

export const MediaDownloadHistoryPageReadSchema = z.looseObject({
  items: z.array(MediaDownloadHistoryEntryReadSchema),
  total: z.int(),
  offset: z.int(),
  limit: z.int(),
  hasMore: z.boolean(),
})

export type MediaDownloadHistoryEntryRead = z.infer<typeof MediaDownloadHistoryEntryReadSchema>
export type MediaDownloadHistoryPageRead = z.infer<typeof MediaDownloadHistoryPageReadSchema>
