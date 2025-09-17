// A single server error item
export type ServerErrorItem = {
    loc?: (string | number)[];
    type?: string;   // e.g. "unique_violation", "string_too_short"
    msg?: string;    // backend fallback
};

// Per-form overrides: field -> (type -> message)
export type FieldOverrides = Record<string, Record<string, string>>;

/**
 * Only return a message when you have an override for (field, type).
 * Otherwise, return undefined so the caller can use defaults.
 */
export function createServerErrorMapper(overrides: FieldOverrides) {
    return (err: ServerErrorItem, field: string): string | undefined => {
        const byField = overrides[field];
        if (!byField) return undefined;
        const type = err.type ?? "";
        return byField[type]; // might be undefined
    };
}
