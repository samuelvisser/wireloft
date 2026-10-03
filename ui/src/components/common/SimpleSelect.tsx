import {forwardRef} from 'react'
import Select, {type Props as ReactSelectProps, type SelectInstance} from 'react-select'

import type {SelectRegistry} from '../../utils/selectRegistry'

type SimpleSelectOption = {
    value: string
    label: string
}

type SimpleSelectProps = Omit<
    ReactSelectProps<SimpleSelectOption, false>,
    'options' | 'value' | 'onChange' | 'isMulti' | 'isSearchable' | 'isClearable'
> & {
    registry: SelectRegistry
    value?: string | null
    onChange?: (value: string) => void
}

/**
 * A registry-backed ReactSelect for controls that should behave like a native select:
 * one value, no search, and no clear action.
 *
 * If a selector needs more advanced ReactSelect features such as searching, clearing,
 * multi-select, custom option rendering, or async behavior, use react-select's Select
 * directly instead of expanding this intentionally simple component.
 */
const SimpleSelect = forwardRef<SelectInstance<SimpleSelectOption, false>, SimpleSelectProps>(
    function SimpleSelect({
        registry,
        value,
        onChange,
        classNamePrefix = 'select',
        ...props
    }, ref) {
        const selectedOption = registry.options.find((option) => option.value === value) ?? null

        return (
            <Select<SimpleSelectOption, false>
                {...props}
                ref={ref}
                classNamePrefix={classNamePrefix}
                options={registry.options}
                value={selectedOption}
                onChange={(option) => {
                    if (option) onChange?.(option.value)
                }}
                isMulti={false}
                isSearchable={false}
                isClearable={false}
            />
        )
    },
)

export default SimpleSelect
