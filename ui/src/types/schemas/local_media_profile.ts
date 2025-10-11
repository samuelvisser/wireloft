import {z} from "zod";
import {createServerErrorMapper} from "../../utils/serverMessageMap";
import {PreferredFormatReg} from "../local_media_profile";

// Only override what you care about for this form.
export const LocalMediaProfileServerErrors = createServerErrorMapper({
    name: {unique_violation: "Name is already taken."},
    slug: {unique_violation: "Slug is already taken."},
});

// ---------- Strict request (create/update) ----------
const LocalMediaProfileBaseSchema = z.object({
    name: z.string().min(1, "Name is required"),
    outputTemplate: z.string()
        .regex(/^\/downloads\//, "Output template must start with '/downloads/'")
        .regex(/\.ext$/, "Output template must end with '.ext'")
        .min(16),
    preferredFormat: z.enum(PreferredFormatReg.values),
    downloadSeriesImages: z.boolean(),
})


export const LocalMediaProfileCreateSchema = LocalMediaProfileBaseSchema.extend({
    outputTemplate: LocalMediaProfileBaseSchema.shape.outputTemplate.default('/downloads/'),
    preferredFormat: LocalMediaProfileBaseSchema.shape.preferredFormat.default('format_1080p'),
    downloadSeriesImages: LocalMediaProfileBaseSchema.shape.downloadSeriesImages.default(true),
})
export type LocalMediaProfileCreateIn = z.input<typeof LocalMediaProfileCreateSchema>;
export type LocalMediaProfileCreateOut = z.output<typeof LocalMediaProfileCreateSchema>;


export const LocalMediaProfileUpdateSchema = LocalMediaProfileBaseSchema.extend({
    id: z.int(),
    slug: z.string(),
})
export type LocalMediaProfileUpdateIn = z.input<typeof LocalMediaProfileUpdateSchema>;
export type LocalMediaProfileUpdateOut = z.output<typeof LocalMediaProfileUpdateSchema>;


// ------------ Lenient response (read) ------------
export const LocalMediaProfileReadSchema = z.looseObject({
    id: z.int(),
    slug: z.string(),
    name: z.string(),
    outputTemplate: z.string(),
    preferredFormat: z.union([z.enum(PreferredFormatReg.values), z.string()]),
    downloadSeriesImages: z.boolean(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type LocalMediaProfileRead = z.infer<typeof LocalMediaProfileReadSchema>;
