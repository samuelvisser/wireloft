import {z} from "zod";

export function getZodDefaults<Schema extends z.core.$ZodLooseShape>(schema: Schema): Partial<z.input<Schema>> {
    if (!(schema instanceof z.ZodObject)) return {}

    const shape = schema.shape
    const entries = Object.entries(shape).map(([key, value]) => {
        if (value instanceof z.ZodDefault) {
            return [key, value.def.defaultValue]
        }
        return [key, undefined]
    })
    return Object.fromEntries(entries) as Partial<z.input<Schema>>
}