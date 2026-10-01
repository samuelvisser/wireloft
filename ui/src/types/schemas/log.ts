import {z} from 'zod'
import {ApiDateTimeStringSchema} from './datetime'

export const ApplicationLogEntryReadSchema = z.looseObject({
  id: z.int(),
  timestamp: ApiDateTimeStringSchema,
  level: z.string(),
  logger: z.string(),
  message: z.string(),
  exception: z.string().nullable().optional(),
})
export type ApplicationLogEntryRead = z.infer<typeof ApplicationLogEntryReadSchema>

export const ApplicationLogPageReadSchema = z.looseObject({
  items: z.array(ApplicationLogEntryReadSchema),
  total: z.int(),
  retainedLimit: z.int(),
})
export type ApplicationLogPageRead = z.infer<typeof ApplicationLogPageReadSchema>
