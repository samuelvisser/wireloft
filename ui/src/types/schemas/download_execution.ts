import {z} from 'zod'

export const DownloadWaitSchema = z.object({
    reason: z.string(),
    started_at: z.number().optional(),
    finished_at: z.number().nullable().optional(),
    until: z.number().nullable().optional(),
})

export const DownloadStageSchema = z.object({
    id: z.string(), code: z.string(), phase: z.string(), resource: z.string(),
    weight: z.number(), asset_id: z.string().nullable().optional(),
    state: z.enum(['pending', 'running', 'waiting', 'completed', 'skipped', 'failed', 'canceled']),
    started_at: z.number().nullable(), finished_at: z.number().nullable(),
    fraction: z.number().nullable(), bytes_received: z.number(), total_bytes: z.number().nullable(),
    segments_done: z.number().nullable(), segments_total: z.number().nullable(),
    wait: DownloadWaitSchema.nullable(), waits: DownloadWaitSchema.array(),
    last_activity_at: z.number().nullable(), deadline_at: z.number().nullable(),
})

export const DownloadExecutionSchema = z.object({
    attempt_id: z.string(), sequence: z.int(),
    phase: z.enum(['preparing', 'transferring', 'finishing', 'complete']),
    main_activity: z.string(), stages: DownloadStageSchema.array(),
    started_at: z.number(), heartbeat_at: z.number(), last_activity_at: z.number(),
    primary_transfer_complete: z.boolean(), canceling: z.boolean(),
    preparation_steps: z.object({code: z.string(), started_at: z.number(), finished_at: z.number()}).array(),
    warnings: z.string().array(),
})
export type DownloadExecution = z.infer<typeof DownloadExecutionSchema>
export type DownloadStage = z.infer<typeof DownloadStageSchema>
