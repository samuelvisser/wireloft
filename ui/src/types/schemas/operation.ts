import {z} from 'zod'

export const TaskOperationResultSchema = z.looseObject({
  summary: z.string(),
  data: z.record(z.string(), z.unknown()).default({}),
})

export const TaskOperationReadSchema = z.looseObject({
  id: z.string(),
  kind: z.string(),
  source: z.string(),
  resourceType: z.string(),
  resourceId: z.int().nullable(),
  title: z.string(),
  status: z.string(),
  progress: z.int().nullable().optional(),
  progressCurrent: z.int(),
  progressTotal: z.int(),
  message: z.string().nullable().optional(),
  result: TaskOperationResultSchema.nullable().optional(),
  context: z.record(z.string(), z.unknown()).nullable().optional(),
  error: z.string().nullable().optional(),
  notificationSeenAt: z.string().nullable().optional(),
  startedAt: z.string().nullable().optional(),
  finishedAt: z.string().nullable().optional(),
  createdAt: z.string().nullable().optional(),
  updatedAt: z.string().nullable().optional(),
})

export type TaskOperationResult = z.infer<typeof TaskOperationResultSchema>
export type TaskOperationRead = z.infer<typeof TaskOperationReadSchema>
