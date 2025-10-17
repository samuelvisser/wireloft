import {z} from "zod";
import {DailywireSeasonReadSchema} from "./dailywire_season";
import {DailywireEpisodeReadSchema} from "./dailywire_episode";


// ---------- Lenient response (read) ----------
export const DailywireShowReadSchema = z.object({
    dwId: z.string().min(1, "dwId missing").default(''),
    slug: z.string().min(1, "slug missing").default(''),
    title: z.string().min(1, "title missing").default(''),
    description: z.string().nullable(),
    backgroundImagePath: z.string().nullable(),
    logoImagePath: z.string().nullable(),
    sharingUrl: z.string(),

    authorName: z.string().min(1, "authorName missing").default(''),
    authorSlug: z.string().min(1, "authorSlug missing").default(''),
    authorHeadshotPath: z.string().nullable(),

    thumbnailLandscapePath: z.string().nullable(),
    thumbnailPortraitPath: z.string().nullable(),
    thumbnailSquarePath: z.string().nullable(),

    latestSeason: z.object(DailywireSeasonReadSchema),
    seasons: z.array(DailywireSeasonReadSchema),

    latestEpisode: z.object(DailywireEpisodeReadSchema),
    latestEpisodes: z.array(DailywireEpisodeReadSchema),

    probableShowType: z.string(),
    probablyEpisodeIdentification: z.string(),
});
export type DailywireShowRead = z.infer<typeof DailywireShowReadSchema>;




