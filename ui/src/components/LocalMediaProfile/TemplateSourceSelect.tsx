import {useMemo} from 'react'
import Select, {createFilter, type GroupBase} from 'react-select'

import type {
    LocalMediaProfileTemplateSource,
    LocalMediaProfileTemplateSourceMode,
} from '../../lib/localMediaProfileTemplateSources'
import './TemplateSourceSelect.css'

type Props = {
    mode: LocalMediaProfileTemplateSourceMode
    sources: LocalMediaProfileTemplateSource[]
    selectedSourceId: string
    onChange: (sourceId: string) => void
}

type SourceOption = {
    value: string
    label: string
    fullLabel: string
}

type SourceGroup = GroupBase<SourceOption>

const filterSourceOption = createFilter<SourceOption>({
    stringify: ({data}) => data.fullLabel,
})

function optionForSource(
    source: LocalMediaProfileTemplateSource,
    mode: LocalMediaProfileTemplateSourceMode,
): SourceOption {
    if (mode !== 'show') {
        return {
            value: source.id,
            label: source.label,
            fullLabel: source.label,
        }
    }

    const showTitle = source.values.show_title?.trim()
    const episodeTitle = source.values.episode_title?.trim()
    if (!showTitle || !episodeTitle) {
        return {
            value: source.id,
            label: source.label,
            fullLabel: source.label,
        }
    }

    return {
        value: source.id,
        label: episodeTitle,
        fullLabel: `${showTitle} — ${episodeTitle}`,
    }
}

export default function TemplateSourceSelect({
    mode,
    sources,
    selectedSourceId,
    onChange,
}: Props) {
    const options = useMemo<readonly (SourceOption | SourceGroup)[]>(() => {
        if (mode !== 'show') {
            return sources.map((source) => optionForSource(source, mode))
        }

        const groups = new Map<string, SourceOption[]>()
        for (const source of sources) {
            const showTitle = source.values.show_title?.trim() || 'Other examples'
            const optionsForShow = groups.get(showTitle) ?? []
            optionsForShow.push(optionForSource(source, mode))
            groups.set(showTitle, optionsForShow)
        }

        return [...groups.entries()].map(([label, groupOptions]) => ({
            label,
            options: groupOptions,
        }))
    }, [mode, sources])

    const selectedOption = useMemo(() => {
        for (const source of sources) {
            if (source.id === selectedSourceId) return optionForSource(source, mode)
        }
        return null
    }, [mode, selectedSourceId, sources])

    return (
        <Select<SourceOption, false, SourceGroup>
            inputId="template-example-source"
            className="template-source-select"
            classNamePrefix="select"
            options={options}
            value={selectedOption}
            onChange={(option) => option && onChange(option.value)}
            filterOption={filterSourceOption}
            isClearable={false}
            isSearchable={sources.length > 7}
            maxMenuHeight={360}
            menuPlacement="auto"
            formatOptionLabel={(option, {context}) => (
                context === 'value' ? option.fullLabel : option.label
            )}
            formatGroupLabel={(group) => (
                <div className="template-source-group-heading">
                    <span>{group.label}</span>
                    <span className="template-source-group-count">{group.options.length}</span>
                </div>
            )}
            aria-label="Example source"
        />
    )
}
