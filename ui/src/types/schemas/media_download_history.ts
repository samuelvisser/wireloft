import {z} from 'zod'
import {ApiDateTimeStringSchema} from './datetime'

export const MediaDownloadHistoryEntryReadSchema = z.looseObject({
  id: z.int(),
  mediaDownloadId: z.int(),
  action: z.string(),
  label: z.string(),
  status: z.string(),
  occurredAt: ApiDateTimeStringSchema,
  durationMs: z.int().nullable(),
  duration: z.string().nullable(),
  detail: z.string().nullable(),
  metadata: z.record(z.string(), z.unknown()),
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
