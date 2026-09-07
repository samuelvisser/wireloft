import {z} from 'zod'
import {DwMembershipLevelReg} from "../dailywire_user_info";
import {ApiDateTimeSchema} from './datetime'

export const DailywireUserInfoReadSchema = z.looseObject({
    personId: z.string(),
    subscriptionId: z.string(),
    username: z.string(),
    email: z.string(),
    firstName: z.string(),
    lastName: z.string(),
    avatar: z.string(),
    accessLevel: z.union([z.enum(DwMembershipLevelReg.Enum), z.string()]),
    planType: z.union([z.enum(DwMembershipLevelReg.Enum), z.string()]),
    accountCreatedAt: ApiDateTimeSchema,
})
export type DailywireUserInfoRead = z.infer<typeof DailywireUserInfoReadSchema>