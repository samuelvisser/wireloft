import {z} from "zod";
import {ApiDateTimeStringSchema} from './datetime'

export const TaskDefinitionReadSchema = z.looseObject({
  id: z.int(),
  key: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  allowedResourceTypes: z.array(z.string()).nullable(),
  defaultMaxRetries: z.int().nullable(),
});
export type TaskDefinitionRead = z.infer<typeof TaskDefinitionReadSchema>;

export const TaskRunWaitStateReadSchema = z.looseObject({
  reason: z.string(),
  message: z.string().nullable().optional(),
  until: z.number().nullable().optional(),
});
export type TaskRunWaitStateRead = z.infer<typeof TaskRunWaitStateReadSchema>;

export const TaskRunReadSchema = z.looseObject({
  id: z.int(),
  definitionKey: z.string(),
  resourceType: z.string(),
  resourceId: z.int(),
  status: z.string(),
  progress: z.int().nullable().optional(),
  waitState: TaskRunWaitStateReadSchema.nullable().optional(),
  message: z.string().nullable().optional(),
  result: z.record(z.string(), z.unknown()).nullable().optional(),
  attemptCount: z.int(),
  maxRetries: z.int(),
  lastError: z.string().nullable().optional(),
  startedAt: ApiDateTimeStringSchema.nullable().optional(),
  finishedAt: ApiDateTimeStringSchema.nullable().optional(),
  runtimeMs: z.number().nullable().optional(),
});
export type TaskRunRead = z.infer<typeof TaskRunReadSchema>;

export const TaskLedgerEntryReadSchema = z.looseObject({
  id: z.int(),
  definitionKey: z.string(),
  definitionTitle: z.string(),
  resourceType: z.string(),
  resourceId: z.int().nullable(),
  status: z.string(),
  progress: z.int().nullable().optional(),
  waitState: TaskRunWaitStateReadSchema.nullable().optional(),
  message: z.string().nullable().optional(),
  lastError: z.string().nullable().optional(),
  inputs: z.record(z.string(), z.unknown()),
  result: z.record(z.string(), z.unknown()).nullable().optional(),
  attemptCount: z.int(),
  maxRetries: z.int(),
  nextRetryAt: ApiDateTimeStringSchema.nullable().optional(),
  startedAt: ApiDateTimeStringSchema.nullable().optional(),
  finishedAt: ApiDateTimeStringSchema.nullable().optional(),
  runtimeMs: z.number().nullable().optional(),
  createdAt: ApiDateTimeStringSchema,
  updatedAt: ApiDateTimeStringSchema,
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
