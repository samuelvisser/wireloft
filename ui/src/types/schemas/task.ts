import {z} from "zod";

// Task run shape as returned by the API (camelCase keys)
export const TaskRunReadSchema = z.looseObject({
  id: z.int(),
  definitionKey: z.string(),
  resourceType: z.string(),
  resourceId: z.int(),
  status: z.string(),
  progress: z.int().nullable().optional(),
  message: z.string().nullable().optional(),
  attemptCount: z.int(),
  maxRetries: z.int(),
  lastError: z.string().nullable().optional(),
  startedAt: z.string().nullable().optional(),
  finishedAt: z.string().nullable().optional(),
  runtimeMs: z.number().nullable().optional(),
});
export type TaskRunRead = z.infer<typeof TaskRunReadSchema>;
