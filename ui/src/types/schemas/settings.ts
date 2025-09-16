import {z} from "zod";

const SettingsBaseSchema = z.object({
})


export const SettingsCreateSchema = SettingsBaseSchema.extend({
})
export type SettingsCreate = z.infer<typeof SettingsCreateSchema>;


export const SettingsReadSchema = SettingsBaseSchema.extend({
    id: z.number(),
    created_at: z.date(),
    updated_at: z.date(),
})
export type SettingsRead = z.infer<typeof SettingsReadSchema>;


export const SettingsUpdateSchema = SettingsBaseSchema.extend({
})
export type SettingsUpdate = z.infer<typeof SettingsUpdateSchema>;