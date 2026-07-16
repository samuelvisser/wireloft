import {z} from "zod";


// ---------- Lenient response (read) ----------
export const DailywireEpisodeReadSchema = z.object({
    dwId: z.string(),
    slug: z.string(),
    title: z.string(),
    description: z.string().nullable(),
    duration: z.number(),
    backgroundImagePath: z.string(),
    sharingUrl: z.string(),
    publishStatus: z.string(),
    isDownloadable: z.boolean(),

    hasFreeAndPaidVideo: z.boolean(),
    isPaidVideo: z.boolean(),

    // Daily Wire's episode numbering. `episodeNumber` is a string like "2460.10"
    // (whole part = episode number, fractional part = segment/variant).
    // `displayEpisodeNumber` is Daily Wire's presentation string (e.g. "Ep. 2324" or "").
    episodeNumber: z.string(),
    displayEpisodeNumber: z.string(),

    thumbnailLandscapePath: z.string().nullable(),
    thumbnailPortraitPath: z.string().nullable(),
    thumbnailSquarePath: z.string().nullable(),

    publishedDate: z.string(),
    scheduledDate: z.string().nullable(),
});
export type DailywireEpisodeRead = z.infer<typeof DailywireEpisodeReadSchema>;




