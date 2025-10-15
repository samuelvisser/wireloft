import {z} from "zod";
import {EpisodeIdentifierReg, ShowTypeReg} from "../show";
import {DwMembershipLevelReg} from "../dailywire_user_info";


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
    .default('')
    .transform(ensureProtocol)
    .transform((s) => {
        try {
            const u = new URL(s);
            return `${u.origin}${u.pathname}`;
        } catch {
            // let the later refinements surface the error
            return s;
        }
    })
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
    membershipLevel: z.enum(DwMembershipLevelReg.Enum).default(DwMembershipLevelReg.Enum.WL_ANY),
    type: z.union([z.enum(ShowTypeReg.values), z.literal('')]).default('')
        .pipe(z.enum(ShowTypeReg.values)),
    episodeIdentifier: z.union([z.enum(EpisodeIdentifierReg.values), z.literal('')]).default('')
        .pipe(z.enum(EpisodeIdentifierReg.values)),
});

export const ShowCreateFormSchema = ShowBaseFormSchema.extend({})
export type ShowCreateFormIn = z.input<typeof ShowCreateFormSchema>;
export type ShowCreateFormOut = z.output<typeof ShowCreateFormSchema>;


export const ShowUpdateFormSchema = ShowBaseFormSchema.extend({})
export type ShowUpdateFormIn = z.input<typeof ShowUpdateFormSchema>;
export type ShowUpdateFormOut = z.output<typeof ShowUpdateFormSchema>;


/* ------------------------------------------------------------------ */
/* 2) DAILYWIRE schema (what the Dailywire API returns)               */
/*    These are NOT user-editable; we compute them from the URL.      */
/* ------------------------------------------------------------------ */
export const ShowDailywireSchema = z.object({
    dwId: z.string().min(1, "dwId missing").default(''),
    slug: z.string().min(1, "slug missing").default(''),
    authorSlug: z.string().min(1, "authorSlug missing").default(''),

    // Content metadata from external API:
    title: z.string().min(1, "title missing").default(''),
    description: z.string().min(1, "description missing").default(''),
    authorName: z.string().min(1, "authorName missing").default(''),

    // Optional image paths:
    authorHeadshotPath: z.string().nullable(),
    backgroundImagePath: z.string().nullable(),
    logoImagePath: z.string().nullable(),
    thumbnailLandscapePath: z.string().nullable(),
    thumbnailPortraitPath: z.string().nullable(),
    thumbnailSquarePath: z.string().nullable(),
});
export type ShowDailywireIn = z.input<typeof ShowDailywireSchema>;
export type ShowDailywireOut = z.output<typeof ShowDailywireSchema>;


/* ------------------------------------------------------------------ */
/* 3) PAYLOAD schema (what we POST to the backend)                    */
/* ------------------------------------------------------------------ */
export const ShowCreatePayloadSchema = ShowCreateFormSchema.extend(ShowDailywireSchema.shape);
export type ShowCreatePayloadIn = z.input<typeof ShowCreatePayloadSchema>;
export type ShowCreatePayloadOut = z.output<typeof ShowCreatePayloadSchema>;


export const ShowUpdatePayloadSchema = ShowUpdateFormSchema.extend(ShowDailywireSchema.shape);
export type ShowUpdatePayloadIn = z.input<typeof ShowUpdatePayloadSchema>;
export type ShowUpdatePayloadOut = z.output<typeof ShowUpdatePayloadSchema>;


/* ------------------------------------------------------------------ */
/* 4) READ schema (lenient response)                                   */
/* ------------------------------------------------------------------ */
export const ShowReadSchema = z.looseObject({
    id: z.int(),
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
