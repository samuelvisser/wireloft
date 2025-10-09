import { z } from 'zod'

// 1) Device authorization initiation response
export const DeviceAuthResponseSchema = z.object({
  deviceCode: z.string(),
  userCode: z.string(),
  verificationUri: z.string(),
  verificationUriComplete: z.string().nullable().optional(),
  expiresIn: z.int().positive(),
  interval: z.int().positive(),
})
export type DeviceAuthResponse = z.infer<typeof DeviceAuthResponseSchema>

// 2) Poll response
export const PollResponseSchema = z.object({
  status: z.enum(['authorized', 'expired', 'denied']),
  message: z.string(),
})
export type PollResponse = z.infer<typeof PollResponseSchema>

// 3) Status response
export const StatusResponseSchema = z.object({
  authenticated: z.boolean(),
  containsRefreshToken: z.boolean(),
  expiresAt: z.number().nullable().optional().default(null),
})
export type StatusResponse = z.infer<typeof StatusResponseSchema>
