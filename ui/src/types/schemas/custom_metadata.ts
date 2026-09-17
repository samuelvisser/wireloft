import {z} from 'zod'

export const CUSTOM_METADATA_KEY_PATTERN = /^[a-z_][a-z0-9_]*$/
export const CUSTOM_METADATA_KEY_MAX_LENGTH = 64
export const CUSTOM_METADATA_VALUE_MAX_LENGTH = 4096
export const CUSTOM_METADATA_MAX_ITEMS = 100

export const CustomMetadataEntrySchema = z.object({
    key: z.string()
        .min(1, 'Field name is required')
        .max(CUSTOM_METADATA_KEY_MAX_LENGTH, `Field name may be at most ${CUSTOM_METADATA_KEY_MAX_LENGTH} characters`)
        .regex(
            CUSTOM_METADATA_KEY_PATTERN,
            'Use lowercase letters, numbers, and underscores; start with a letter or underscore',
        ),
    value: z.string().max(
        CUSTOM_METADATA_VALUE_MAX_LENGTH,
        `Value may be at most ${CUSTOM_METADATA_VALUE_MAX_LENGTH} characters`,
    ),
})

export const CustomMetadataFormSchema = z.object({
    entries: z.array(CustomMetadataEntrySchema).max(
        CUSTOM_METADATA_MAX_ITEMS,
        `At most ${CUSTOM_METADATA_MAX_ITEMS} metadata fields are allowed`,
    ),
}).superRefine(({entries}, ctx) => {
    const seen = new Set<string>()
    entries.forEach((entry, index) => {
        if (seen.has(entry.key)) {
            ctx.addIssue({
                code: 'custom',
                path: ['entries', index, 'key'],
                message: 'Metadata field names must be unique',
            })
        }
        seen.add(entry.key)
    })
})

export type CustomMetadataFormValues = z.infer<typeof CustomMetadataFormSchema>

export function customMetadataToEntries(
    metadata: Record<string, string>,
    fields: readonly string[] = [],
): CustomMetadataFormValues['entries'] {
    const keys = new Set([...fields, ...Object.keys(metadata)])
    return [...keys]
        .sort((left, right) => left.localeCompare(right))
        .map((key) => ({key, value: metadata[key] ?? ''}))
}

export function entriesToCustomMetadata(entries: CustomMetadataFormValues['entries']): Record<string, string> {
    return Object.fromEntries(entries.map(({key, value}) => [key, value]))
}
