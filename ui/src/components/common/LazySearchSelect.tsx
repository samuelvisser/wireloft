import {useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react'
import Select, {components, type GroupBase, type MenuListProps} from 'react-select'

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
    const previousPageScrollPosition = useRef<{height: number; top: number} | null>(null)
    const nextPageRequested = useRef(false)
    const menuListRef = useRef<HTMLDivElement | null>(null)
    const paginationState = useRef({
        hasMore,
        hasPrevious,
        isLoading,
        onLoadMore,
        onLoadPrevious,
    })
    paginationState.current = {
        hasMore,
        hasPrevious,
        isLoading,
        onLoadMore,
        onLoadPrevious,
    }

    const menuListElement = () => menuListRef.current

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

    const handleMenuScroll = useCallback((menuList: HTMLElement) => {
        const {
            hasMore: canLoadMore,
            hasPrevious: canLoadPrevious,
            isLoading: loading,
            onLoadMore: loadMore,
            onLoadPrevious: loadPrevious,
        } = paginationState.current
        if (loading) return

        if (
            menuList.scrollTop <= 1
            && canLoadPrevious
            && loadPrevious
            && previousPageScrollPosition.current === null
        ) {
            previousPageScrollPosition.current = {
                height: menuList.scrollHeight,
                top: menuList.scrollTop,
            }
            loadPrevious()
            return
        }

        const remaining = menuList.scrollHeight - menuList.clientHeight - menuList.scrollTop
        if (remaining <= 1 && canLoadMore && !nextPageRequested.current) {
            nextPageRequested.current = true
            loadMore()
        }
    }, [])

    const MenuList = useCallback((
        props: MenuListProps<LazySearchSelectOption, false, GroupBase<LazySearchSelectOption>>,
    ) => {
        const innerRef = props.innerRef
        const innerOnScroll = props.innerProps.onScroll
        return (
            <components.MenuList
                {...props}
                innerRef={(element) => {
                    menuListRef.current = element
                    if (typeof innerRef === 'function') innerRef(element)
                }}
                innerProps={{
                    ...props.innerProps,
                    onScroll: (event) => {
                        innerOnScroll?.(event)
                        handleMenuScroll(event.currentTarget)
                    },
                }}
            />
        )
    }, [handleMenuScroll])

    const selectComponents = useMemo(() => ({MenuList}), [MenuList])

    useEffect(() => {
        onSearchChangeRef.current = onSearchChange
    }, [onSearchChange])

    useEffect(() => {
        if (!isLoading) {
            if (previousPageScrollPosition.current !== null) {
                previousPageScrollPosition.current = null
            }
            nextPageRequested.current = false
        }
    }, [isLoading])

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
        const previousPosition = previousPageScrollPosition.current
        if (previousPosition === null) return

        const menuList = menuListElement()
        previousPageScrollPosition.current = null
        if (!menuList) return

        const addedHeight = menuList.scrollHeight - previousPosition.height
        if (addedHeight <= 0) return

        // Keep the same content at the same visual position. The newly
        // prepended page then exists directly above the current viewport,
        // without triggering another page load until the user scrolls there.
        menuList.scrollTop = previousPosition.top + addedHeight
    }, [groupedOptions])

    useLayoutEffect(() => {
        nextPageRequested.current = false
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
                previousPageScrollPosition.current = null
                nextPageRequested.current = false
                menuListRef.current = null
            }}
            components={selectComponents}
            captureMenuScroll={false}
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
