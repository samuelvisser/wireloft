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
  result: z.record(z.string(), z.unknown()).nullable().optional(),
  attemptCount: z.int(),
  maxRetries: z.int(),
  lastError: z.string().nullable().optional(),
  startedAt: z.string().nullable().optional(),
  finishedAt: z.string().nullable().optional(),
  runtimeMs: z.number().nullable().optional(),
});
export type TaskRunRead = z.infer<typeof TaskRunReadSchema>;

export const TaskLedgerEntryReadSchema = z.looseObject({
  id: z.int(),
  definitionKey: z.string(),
  resourceType: z.string(),
  resourceId: z.int().nullable(),
  status: z.string(),
  message: z.string().nullable().optional(),
  lastError: z.string().nullable().optional(),
  inputs: z.record(z.string(), z.unknown()),
  result: z.record(z.string(), z.unknown()).nullable().optional(),
  startedAt: z.string().nullable().optional(),
  finishedAt: z.string().nullable().optional(),
  runtimeMs: z.number().nullable().optional(),
});
export type TaskLedgerEntryRead = z.infer<typeof TaskLedgerEntryReadSchema>;

export const TaskLedgerPageReadSchema = z.looseObject({
  items: z.array(TaskLedgerEntryReadSchema),
  total: z.int(),
  offset: z.int(),
  limit: z.int(),
  hasMore: z.boolean(),
});
export type TaskLedgerPageRead = z.infer<typeof TaskLedgerPageReadSchema>;
