import {z} from 'zod'
import {ApiDateTimeStringSchema} from './datetime'
import {TaskLedgerEntryReadSchema} from './task'

export const MediaDownloadTaskHistoryEntryReadSchema = TaskLedgerEntryReadSchema.extend({
  source: z.literal('task'),
})

export const MediaDownloadArtifactHistoryEntryReadSchema = z.looseObject({
  source: z.literal('artifact'),
  artifactStatus: z.enum(['absent', 'available', 'missing', 'corrupted']),
  artifactError: z.string().nullable(),
  filePath: z.string(),
  observedAt: ApiDateTimeStringSchema,
})

export const MediaDownloadEventHistoryEntryReadSchema = z.looseObject({
  source: z.literal('event'),
  id: z.int(),
  eventType: z.enum(['deleted']),
  filePath: z.string(),
  occurredAt: ApiDateTimeStringSchema,
})

export const MediaDownloadHistoryEntryReadSchema = z.discriminatedUnion('source', [
  MediaDownloadTaskHistoryEntryReadSchema,
  MediaDownloadArtifactHistoryEntryReadSchema,
  MediaDownloadEventHistoryEntryReadSchema,
])

export const MediaDownloadHistoryPageReadSchema = z.looseObject({
  items: z.array(MediaDownloadHistoryEntryReadSchema),
  total: z.int(),
  offset: z.int(),
  limit: z.int(),
  hasMore: z.boolean(),
})

export type MediaDownloadHistoryEntryRead = z.infer<typeof MediaDownloadHistoryEntryReadSchema>
export type MediaDownloadHistoryPageRead = z.infer<typeof MediaDownloadHistoryPageReadSchema>
