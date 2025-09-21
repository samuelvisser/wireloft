import {z} from "zod";

export function getZodDefaults<Schema extends z.core.$ZodLooseShape>(schema: Schema) {
    return Object.fromEntries(
        Object.entries(schema.shape).map(([key, value]) => {
            if (value instanceof z.ZodDefault) return [key, value.def.defaultValue]
            return [key, undefined]
        })
    )
}