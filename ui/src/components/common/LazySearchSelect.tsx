import {useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react'
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
    hasPrevious?: boolean
    onChange: (option: LazySearchSelectOption) => void
    onSearchChange: (search: string) => void
    onLoadMore: () => void
    onLoadPrevious?: () => void
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
    hasPrevious = false,
    onChange,
    onSearchChange,
    onLoadMore,
    onLoadPrevious,
    placeholder = 'Search…',
    noOptionsMessage = 'No results found',
    debounceMs = 250,
    maxMenuHeight = 360,
    ariaLabel,
}: Props) {
    const [inputValue, setInputValue] = useState('')
    const onSearchChangeRef = useRef(onSearchChange)
    const scrollSelectedWhenAvailable = useRef(false)
    const previousPageScrollHeight = useRef<number | null>(null)

    const menuListElement = () => {
        const input = document.getElementById(inputId)
        return input
            ?.closest(`.${classNamePrefix}__control`)
            ?.parentElement
            ?.querySelector<HTMLElement>(`.${classNamePrefix}__menu-list`) ?? null
    }

    const scrollSelectedIntoView = () => {
        // React Select performs its own selected-option scroll while opening.
        // Wait until that has settled, then center the option within the menu.
        window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
                if (!scrollSelectedWhenAvailable.current) return
                const menuList = menuListElement()
                const selected = menuList
                    ?.querySelector<HTMLElement>(`.${classNamePrefix}__option--is-selected`)
                if (!menuList || !selected) return

                const menuRect = menuList.getBoundingClientRect()
                const selectedRect = selected.getBoundingClientRect()
                const selectedCenter = (
                    menuList.scrollTop
                    + selectedRect.top
                    - menuRect.top
                    + selectedRect.height / 2
                )
                menuList.scrollTop = selectedCenter - menuList.clientHeight / 2
                scrollSelectedWhenAvailable.current = false
            })
        })
    }

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

    useLayoutEffect(() => {
        const previousHeight = previousPageScrollHeight.current
        if (previousHeight === null) return

        const menuList = menuListElement()
        previousPageScrollHeight.current = null
        if (!menuList) return

        const addedHeight = menuList.scrollHeight - previousHeight
        if (addedHeight <= 0 || menuList.scrollTop <= 0) return

        // Browsers that preserve the old first visible option after a prepend
        // move scrollTop down by the inserted height. Reveal one viewport of the
        // newly loaded page immediately instead of requiring another gesture.
        menuList.scrollTop = Math.max(
            0,
            menuList.scrollTop - Math.min(addedHeight, menuList.clientHeight),
        )
    }, [groupedOptions])

    useEffect(() => {
        if (scrollSelectedWhenAvailable.current) scrollSelectedIntoView()
    }, [groupedOptions])

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
            onMenuOpen={() => {
                scrollSelectedWhenAvailable.current = true
                scrollSelectedIntoView()
            }}
            onMenuClose={() => {
                scrollSelectedWhenAvailable.current = false
                previousPageScrollHeight.current = null
            }}
            onMenuScrollToTop={() => {
                if (!hasPrevious || isLoading || !onLoadPrevious) return
                const menuList = menuListElement()
                if (!menuList) return
                previousPageScrollHeight.current = menuList.scrollHeight
                onLoadPrevious()
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
