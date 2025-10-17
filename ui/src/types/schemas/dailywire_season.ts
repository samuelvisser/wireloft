import {z} from "zod";


export const DailywireSeasonReadSchema = z.looseObject({
    dwId: z.string(),
    slug: z.string(),
    title: z.string()
});
export type DailywireSeasonRead = z.infer<typeof DailywireSeasonReadSchema>;
