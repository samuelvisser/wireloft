import {z} from "zod";


// ---------- Strict request (create/update) ----------
const SettingsBaseSchema = z.object({
})


export const SettingsCreateSchema = SettingsBaseSchema.extend({
})
export type SettingsCreateIn = z.input<typeof SettingsCreateSchema>;
export type SettingsCreateOut = z.output<typeof SettingsCreateSchema>;


export const SettingsUpdateSchema = SettingsBaseSchema.extend({
})
export type SettingsUpdateIn = z.input<typeof SettingsUpdateSchema>;
export type SettingsUpdateOut = z.output<typeof SettingsUpdateSchema>;


// ------------ Lenient response (read) ------------
export const SettingsReadSchema = z.looseObject({
    id: z.number(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type SettingsRead = z.infer<typeof SettingsReadSchema>;