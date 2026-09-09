import {ShowTypeReg, ShowTypeValue} from '../../types/show'

const DEFAULT_SHOW_TYPE_FILTER = new Set<ShowTypeValue>(ShowTypeReg.values)

export function createDefaultShowTypeFilter(): Set<ShowTypeValue> {
    return new Set(DEFAULT_SHOW_TYPE_FILTER)
}

function setsEqual(a: ReadonlySet<ShowTypeValue>, b: ReadonlySet<ShowTypeValue>): boolean {
    if (a.size !== b.size) return false
    for (const value of a) if (!b.has(value)) return false
    return true
}

export function matchesShowTypeFilter(
    type: unknown,
    selectedTypes: ReadonlySet<ShowTypeValue>,
): boolean {
    const normalized = ShowTypeReg.normalize(type)
    return normalized !== null && selectedTypes.has(normalized)
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
            {!setsEqual(selectedTypes, DEFAULT_SHOW_TYPE_FILTER) && (
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
