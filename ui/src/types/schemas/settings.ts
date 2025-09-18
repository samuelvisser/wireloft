import {z} from "zod";


// ---------- Strict request (create/update) ----------
const SettingsBaseSchema = z.object({
})


export const SettingsCreateSchema = SettingsBaseSchema.extend({
})
export type SettingsCreate = z.infer<typeof SettingsCreateSchema>;


export const SettingsUpdateSchema = SettingsBaseSchema.extend({
})
export type SettingsUpdate = z.infer<typeof SettingsUpdateSchema>;


// ------------ Lenient response (read) ------------
export const SettingsReadSchema = z.looseObject({
    id: z.number(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type SettingsRead = z.infer<typeof SettingsReadSchema>;