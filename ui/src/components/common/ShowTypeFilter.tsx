import {ShowTypeReg, ShowTypeValue} from '../../types/show'

export const DEFAULT_SHOW_TYPE_FILTER = new Set<ShowTypeValue>(ShowTypeReg.values)

export function createDefaultShowTypeFilter(): Set<ShowTypeValue> {
    return new Set(DEFAULT_SHOW_TYPE_FILTER)
}

function setsEqual(a: ReadonlySet<ShowTypeValue>, b: ReadonlySet<ShowTypeValue>): boolean {
    if (a.size !== b.size) return false
    for (const value of a) if (!b.has(value)) return false
    return true
}

export function isDefaultShowTypeFilter(selectedTypes: ReadonlySet<ShowTypeValue>): boolean {
    return setsEqual(selectedTypes, DEFAULT_SHOW_TYPE_FILTER)
}

export function matchesShowTypeFilter(
    type: unknown,
    selectedTypes: ReadonlySet<ShowTypeValue>,
): boolean {
    const normalized = ShowTypeReg.normalize(type)
    if (normalized !== null) return selectedTypes.has(normalized)

    // Daily Wire's existing best-effort classifier can return "unknown". An
    // unclassified show belongs to either filter option rather than inventing a
    // second classification rule here. It is only hidden when both are disabled.
    return selectedTypes.size > 0
}

type ShowTypeFilterProps = {
    selectedTypes: ReadonlySet<ShowTypeValue>
    onChange: (selectedTypes: Set<ShowTypeValue>) => void
    ariaLabel?: string
}

export default function ShowTypeFilter({
    selectedTypes,
    onChange,
    ariaLabel = 'Filter shows by type',
}: ShowTypeFilterProps) {
    const toggleType = (type: ShowTypeValue) => {
        const next = new Set(selectedTypes)
        if (next.has(type)) next.delete(type)
        else next.add(type)
        onChange(next)
    }

    return (
        <div className="filter-chip-group" role="group" aria-label={ariaLabel}>
            {ShowTypeReg.options.map((option) => (
                <button
                    key={option.value}
                    type="button"
                    className="filter-chip"
                    aria-pressed={selectedTypes.has(option.value)}
                    onClick={() => toggleType(option.value)}
                >
                    {option.label}
                </button>
            ))}
            {!isDefaultShowTypeFilter(selectedTypes) && (
                <button
                    type="button"
                    className="filter-chip-reset"
                    onClick={() => onChange(createDefaultShowTypeFilter())}
                >
                    Reset filters
                </button>
            )}
        </div>
    )
}
