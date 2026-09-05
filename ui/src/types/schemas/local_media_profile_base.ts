import {z} from 'zod'


// ---------- Strict request (create/update) ----------
export const LocalMediaProfileSchemaRequest = z.object({
    name: z.string().min(1, 'Name is required'),
})

export const LocalMediaProfileCreateBaseSchema = LocalMediaProfileSchemaRequest

export const LocalMediaProfileUpdateBaseSchema = LocalMediaProfileSchemaRequest.extend({
    id: z.int(),
    slug: z.string(),
})

export const LocalMediaProfileOutputTemplateSchema = z.string()
    .regex(/^\/downloads\//, "Output template must start with '/downloads/'")
    .regex(/\.ext$/, "Output template must end with '.ext'")
    .min(16)
    .max(4096)


// ------------ Lenient response (read) ------------
export const LocalMediaProfileSchemaResponse = z.looseObject({
    id: z.int(),
    slug: z.string(),
    name: z.string(),
    outputTemplate: z.string(),
    preferredFormat: z.string(),
    appendMediaTypeToFilename: z.boolean().optional().default(false),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
