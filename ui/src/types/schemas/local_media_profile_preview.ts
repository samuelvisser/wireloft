import {z} from 'zod'

export const LocalMediaProfilePreviewSchema = z.object({
    output: z.object({
        outputPath: z.string().nullable(),
        error: z.string().nullable(),
        usedVariables: z.array(z.string()),
        usedIndexingValues: z.array(z.string()),
        missingIndexingValues: z.array(z.string()),
        provisionalIndexingValues: z.array(z.string()),
    }),
    showRoot: z.object({
        path: z.string().nullable(),
        reason: z.string().nullable(),
        showTitle: z.string().nullable(),
        systemEnabled: z.boolean(),
    }).nullable(),
})
export type LocalMediaProfilePreview = z.infer<typeof LocalMediaProfilePreviewSchema>
