type OptionMeta = {
    label: string;
    help?: string;
    /** Alternative spellings you may receive (case-insensitive). */
    aliases?: string[];
};

type SelectRegistrySpec<T extends string> = Record<T, OptionMeta>;

export type SelectRegistry = ReturnType<typeof createSelectRegistry>;

export function createSelectRegistry<const T extends string>(name: string, spec: SelectRegistrySpec<T>) {
    // Values are the keys of the spec, in declaration order
    const values = Object.keys(spec) as T[];

    // Maps for quick lookup
    const valueSet = new Set<T>(values);
    const aliasMap = new Map<string, T>();
    for (const v of values) {
        aliasMap.set(v.toLowerCase(), v);
        for (const a of spec[v].aliases ?? []) aliasMap.set(a.toLowerCase(), v);
    }

    const options = values.map((v) => ({value: v, label: spec[v].label}));

    // Normalize unknown → T | null (accepts value or any alias; case-insensitive)
    const normalize = (x: unknown): T | null => {
        if (typeof x !== "string") return null;
        const hit: T | undefined = aliasMap.get(x.trim().toLowerCase());
        return hit ?? null;
    };

    // Enum-like object (keys === values), fully typed and immutable
    const Enum = Object.freeze(
        Object.fromEntries(values.map((v) => [v, v])) as { readonly [K in T]: K }
    );

    // Type guard
    const is = (x: unknown): x is T => normalize(x) !== null;

    // Convenience accessors
    const meta = (v: T) => spec[v];

    // Returns the label for the given value, or throws if not found
    const getLabel = (v: T) => spec[v].label;

    // Returns the label for the given value, or the value itself if not found
    const getLabelLoose = (x: T | string) => {
        const n = normalize(x);
        if (n !== null) return spec[n].label;
        return x
    }

    // Helpful string for debugging
    const describe = () => `${name}(${values.join(", ")})`;

    return {
        name,
        values: values as readonly T[],
        valueSet,
        spec,
        options,
        normalize,
        Enum,
        is,
        meta,
        getLabel,
        getLabelLoose,
        describe,
    };
}