import {useEffect, useMemo, useRef, useState} from 'react'
import Select, {type GroupBase} from 'react-select'

export type LazySearchSelectOption = {
    value: string
    label: string
    selectedLabel?: string
    group?: string
}

type Props = {
    inputId: string
    className?: string
    classNamePrefix?: string
    options: LazySearchSelectOption[]
    value: LazySearchSelectOption | null
    isLoading: boolean
    hasMore: boolean
    onChange: (option: LazySearchSelectOption) => void
    onSearchChange: (search: string) => void
    onLoadMore: () => void
    placeholder?: string
    noOptionsMessage?: string
    debounceMs?: number
    maxMenuHeight?: number
    ariaLabel?: string
}

export default function LazySearchSelect({
    inputId,
    className,
    classNamePrefix = 'select',
    options,
    value,
    isLoading,
    hasMore,
    onChange,
    onSearchChange,
    onLoadMore,
    placeholder = 'Search…',
    noOptionsMessage = 'No results found',
    debounceMs = 250,
    maxMenuHeight = 360,
    ariaLabel,
}: Props) {
    const [inputValue, setInputValue] = useState('')
    const onSearchChangeRef = useRef(onSearchChange)

    useEffect(() => {
        onSearchChangeRef.current = onSearchChange
    }, [onSearchChange])

    useEffect(() => {
        const timer = window.setTimeout(() => onSearchChangeRef.current(inputValue), debounceMs)
        return () => window.clearTimeout(timer)
    }, [debounceMs, inputValue])

    const groupedOptions = useMemo<readonly (LazySearchSelectOption | GroupBase<LazySearchSelectOption>)[]>(() => {
        const groups = new Map<string, LazySearchSelectOption[]>()
        const ungrouped: LazySearchSelectOption[] = []

        for (const option of options) {
            if (!option.group) {
                ungrouped.push(option)
                continue
            }
            const group = groups.get(option.group) ?? []
            group.push(option)
            groups.set(option.group, group)
        }

        return [
            ...ungrouped,
            ...[...groups.entries()].map(([label, groupOptions]) => ({
                label,
                options: groupOptions,
            })),
        ]
    }, [options])

    return (
        <Select<LazySearchSelectOption, false, GroupBase<LazySearchSelectOption>>
            inputId={inputId}
            className={className}
            classNamePrefix={classNamePrefix}
            options={groupedOptions}
            value={value}
            inputValue={inputValue}
            onInputChange={(nextValue, action) => {
                if (action.action === 'input-change') setInputValue(nextValue)
                return nextValue
            }}
            onChange={(option) => {
                if (!option) return
                setInputValue('')
                onChange(option)
            }}
            onMenuScrollToBottom={() => {
                if (hasMore && !isLoading) onLoadMore()
            }}
            isLoading={isLoading}
            isClearable={false}
            isSearchable
            filterOption={() => true}
            placeholder={placeholder}
            noOptionsMessage={() => isLoading ? 'Searching…' : noOptionsMessage}
            loadingMessage={() => 'Loading…'}
            maxMenuHeight={maxMenuHeight}
            menuPlacement="auto"
            formatOptionLabel={(option, {context}) => (
                context === 'value' ? (option.selectedLabel ?? option.label) : option.label
            )}
            aria-label={ariaLabel}
        />
    )
}
