import {z} from 'zod'
import {ApiDateTimeSchema} from "./datetime";


// ---------- Strict request (create/update) ----------
export const LocalMediaProfileSchemaRequest = z.object({
    name: z.string().min(1, 'Name is required'),
})

export const LocalMediaProfileCreateBaseSchema = LocalMediaProfileSchemaRequest

export const LocalMediaProfileUpdateBaseSchema = LocalMediaProfileSchemaRequest.extend({
    id: z.int(),
    slug: z.string(),
})

const SINGLE_BRACE_OUTPUT_TEMPLATE_VARIABLE = /(^|[^{])\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}(?!\})/

export const LocalMediaProfileOutputTemplateSchema = z.string()
    .refine(
        (value) => !SINGLE_BRACE_OUTPUT_TEMPLATE_VARIABLE.test(value),
        {message: "Output template variables must use Jinja syntax such as '{{ show }}'; single-brace variables are not supported"},
    )
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
    createdAt: ApiDateTimeSchema,
    updatedAt: ApiDateTimeSchema,
})
