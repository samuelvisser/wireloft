import {z} from "zod";


// ---------- Lenient response (read) ----------
export const DailywireEpisodeReadSchema = z.object({
    dwId: z.string(),
    slug: z.string(),
    title: z.string(),
    description: z.string(),
    duration: z.number(),
    backgroundImagePath: z.string(),
    sharingUrl: z.string(),
    publishStatus: z.string(),
    isDownloadable: z.boolean(),

    thumbnailLandscapePath: z.string(),
    thumbnailPortraitPath: z.string(),
    thumbnailSquarePath: z.string(),

    publishedDate: z.string(),
    scheduledDate: z.string(),
});
export type DailywireEpisodeRead = z.infer<typeof DailywireEpisodeReadSchema>;




