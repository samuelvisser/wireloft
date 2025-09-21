import {z} from "zod";
import {EpisodeIdentifierReg, ShowTypeReg} from "../show";


/** Ensure https:// if a scheme is missing */
function ensureProtocol(input: string): string {
    let v = (input ?? "").trim();
    if (!v) return v;
    if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(v)) v = "https://" + v;
    return v;
}

/** DailyWire URL constraints */
const dailyWireUrl = z
    .string()
    .nonempty({message: "URL is required"})
    .transform(ensureProtocol)
    .refine((s) => {
        try {
            const u = new URL(s);
            const host = u.hostname.toLowerCase();
            return host === "dailywire.com" || host === "www.dailywire.com";
        } catch {
            return false;
        }
    }, {message: "URL must be on dailywire.com"})
    .refine((s) => {
        try {
            const u = new URL(s);
            return u.pathname.startsWith("/show/");
        } catch {
            return false;
        }
    }, {message: "URL must include /show/ in the path"})
    .refine((s) => {
        try {
            const u = new URL(s);
            const slug = u.pathname.slice("/show/".length).split("/")[0];
            return !!slug;
        } catch {
            return false;
        }
    }, {message: "URL must include a show name after /show/ (e.g., the-ben-shapiro-show)"});

/* ------------------------------------------------------------------ */
/* FORM schemas (only user-editable fields)                          */
/* ------------------------------------------------------------------ */
const ShowBaseFormSchema = z.object({
    url: dailyWireUrl,
    type: z.union([z.enum(ShowTypeReg.values), z.literal('')])
        .pipe(z.enum(ShowTypeReg.values)),
    episodeIdentifier: z.union([z.enum(EpisodeIdentifierReg.values), z.literal('')])
        .pipe(z.enum(EpisodeIdentifierReg.values)),
});
export type ShowCreateFormInput = z.input<typeof ShowCreateFormSchema>;


export const ShowCreateFormSchema = ShowBaseFormSchema.extend({})
export type ShowCreateForm = z.infer<typeof ShowCreateFormSchema>;


export const ShowUpdateFormSchema = ShowBaseFormSchema.extend({})
export type ShowUpdateForm = z.infer<typeof ShowUpdateFormSchema>;


/* ------------------------------------------------------------------ */
/* 2) DERIVED schema (what the Dailywire API returns)                 */
/*    These are NOT user-editable; we compute them from the URL.      */
/* ------------------------------------------------------------------ */
export const ShowDailywireSchema = z.object({
    // Required by your local API, produced by external API:
    dwId: z.string().min(1, "dwId missing"),
    slug: z.string().min(1, "slug missing"),
    authorSlug: z.string().min(1, "authorSlug missing"),

    // Content metadata from external API:
    title: z.string().min(1, "title missing"),
    description: z.string().min(1, "description missing"),
    authorName: z.string().min(1, "authorName missing"),

    // Optional image paths:
    authorHeadshotPath: z.string().optional(),
    backgroundImagePath: z.string().optional(),
    logoImagePath: z.string().optional(),
    thumbnailLandscapePath: z.string().optional(),
    thumbnailPortraitPath: z.string().optional(),
    thumbnailSquarePath: z.string().optional(),
});
export type ShowDailywire = z.infer<typeof ShowDailywireSchema>;

/* ------------------------------------------------------------------ */
/* 3) PAYLOAD schema (what we POST to the backend)                    */
/* ------------------------------------------------------------------ */
export const ShowCreatePayloadSchema = ShowCreateFormSchema.extend(ShowDailywireSchema.shape);
export type ShowCreatePayload = z.infer<typeof ShowCreatePayloadSchema>;


export const ShowUpdatePayloadSchema = ShowUpdateFormSchema.extend(ShowDailywireSchema.shape);
export type ShowUpdatePayload = z.infer<typeof ShowUpdatePayloadSchema>;


/* ------------------------------------------------------------------ */
/* 4) READ schema (lenient response)                                   */
/* ------------------------------------------------------------------ */
export const ShowReadSchema = z.looseObject({
    id: z.number(),
    uuid: z.string(),
    dwId: z.string(),
    slug: z.string(),
    type: z.union([z.enum(ShowTypeReg.values), z.string()]),
    episodeIdentifier: z.union([z.enum(EpisodeIdentifierReg.values), z.string()]),
    authorSlug: z.string(),
    title: z.string(),
    description: z.string(),
    url: z.string(),
    authorName: z.string(),
    authorHeadshotPath: z.string().optional(),
    backgroundImagePath: z.string().optional(),
    logoImagePath: z.string().optional(),
    thumbnailLandscapePath: z.string().optional(),
    thumbnailPortraitPath: z.string().optional(),
    thumbnailSquarePath: z.string().optional(),
    createdAt: z.iso.datetime().transform((s) => new Date(s)),
    updatedAt: z.iso.datetime().transform((s) => new Date(s)),
})
export type ShowRead = z.infer<typeof ShowReadSchema>;
