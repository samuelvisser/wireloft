import {z} from 'zod'

export const CustomIndexAdvisoryResultSchema = z.object({
    advisories: z.array(z.object({
        key: z.string(),
        message: z.string(),
        suggestion: z.object({
            before: z.string(),
            after: z.string(),
            outputTemplate: z.string(),
        }).nullable(),
    })),
    error: z.string().nullable(),
})

export type CustomIndexAdvisoryResult = z.infer<typeof CustomIndexAdvisoryResultSchema>
