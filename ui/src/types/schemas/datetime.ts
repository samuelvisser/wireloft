import {z} from 'zod'

/**
 * WireLoft API timestamps always represent absolute instants and therefore
 * include either Z or an explicit UTC offset. Parsing them into Date objects at
 * the API boundary lets Intl format them in the browser's local timezone.
 */
export const ApiDateTimeStringSchema = z.iso.datetime({offset: true})
export const ApiDateTimeSchema = ApiDateTimeStringSchema.transform((value) => new Date(value))
