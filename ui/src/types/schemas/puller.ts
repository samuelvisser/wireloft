import {z} from 'zod'
import {TaskOperationReadSchema} from './operation'


export const FrontendPullVersionSchema = z.object({
  appVersion: z.string(),
})

export const FrontendPullDataSchema = z.object({
  operations: TaskOperationReadSchema.array(),
})

export const FrontendPullReadSchema = FrontendPullVersionSchema.extend({
  mode: z.enum(['slow', 'fast']),
  data: FrontendPullDataSchema,
})

export type FrontendPullData = z.infer<typeof FrontendPullDataSchema>
export type FrontendPullRead = z.infer<typeof FrontendPullReadSchema>
