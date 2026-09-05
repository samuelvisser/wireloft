import {z} from 'zod'
import {TaskOperationReadSchema} from './operation'


export const FrontendPullDataSchema = z.object({
  operations: TaskOperationReadSchema.array(),
})

export const FrontendPullReadSchema = z.object({
  mode: z.enum(['slow', 'fast']),
  data: FrontendPullDataSchema,
})

export type FrontendPullData = z.infer<typeof FrontendPullDataSchema>
export type FrontendPullRead = z.infer<typeof FrontendPullReadSchema>
