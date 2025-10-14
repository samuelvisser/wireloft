import {z} from "zod";

export function getZodDefaults<Schema extends z.core.$ZodLooseShape>(schema: Schema): Partial<z.input<Schema>> {
    if (!(schema instanceof z.ZodObject)) return {}

    const shape = schema.shape
    const entries: [string, unknown][] = [];
    for (const [key, value] of Object.entries(shape)) {
        if (value instanceof z.ZodDefault) {
            entries.push([key, value.def.defaultValue])
        }
    }
    return Object.fromEntries(entries) as Partial<z.input<Schema>>
}