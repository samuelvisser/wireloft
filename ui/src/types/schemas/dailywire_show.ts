import {z} from "zod";
import {DailywireSeasonReadSchema} from "./dailywire_season";
import {DailywireEpisodeReadSchema} from "./dailywire_episode";


// ---------- Lenient response (read) ----------
export const DailywireShowReadSchema = z.looseObject({
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

    latestSeason: DailywireSeasonReadSchema,
    seasons: z.array(DailywireSeasonReadSchema),

    latestEpisode: DailywireEpisodeReadSchema,
    latestEpisodes: z.array(DailywireEpisodeReadSchema),

    probableShowType: z.string(),
    probableEpisodeIdentification: z.string(),
});
export type DailywireShowRead = z.infer<typeof DailywireShowReadSchema>;




