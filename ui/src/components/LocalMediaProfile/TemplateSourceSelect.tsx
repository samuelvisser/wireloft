import {useMemo} from 'react'

import LazySearchSelect, {
    type LazySearchSelectOption,
} from '../common/LazySearchSelect'
import type {
    LocalMediaProfileTemplateSource,
    LocalMediaProfileTemplateSourceMode,
} from '../../lib/localMediaProfileTemplateSources'
import {createSelectRegistry} from '../../utils/selectRegistry'
import './TemplateSourceSelect.css'

type Props = {
    mode: LocalMediaProfileTemplateSourceMode
    sources: LocalMediaProfileTemplateSource[]
    selectedSource: LocalMediaProfileTemplateSource | null
    isLoading: boolean
    hasMore: boolean
    hasPrevious?: boolean
    onChange: (source: LocalMediaProfileTemplateSource) => void
    onSearchChange: (search: string) => void
    onLoadMore: () => void
    onLoadPrevious?: () => void
}

function optionForSource(
    source: LocalMediaProfileTemplateSource,
    mode: LocalMediaProfileTemplateSourceMode,
): LazySearchSelectOption {
    if (source.fallback) {
        return {
            value: source.id,
            label: source.label,
            selectedLabel: source.label,
        }
    }

    if (mode === 'show') {
        const showTitle = source.values.show_title?.trim()
        const episodeTitle = source.values.episode_title?.trim()
        return {
            value: source.id,
            label: episodeTitle || source.label,
            selectedLabel: showTitle && episodeTitle
                ? `${showTitle} — ${episodeTitle}`
                : source.label,
            group: showTitle || undefined,
        }
    }

    const movieTitle = source.values.movie_title?.trim()
    const mediaTitle = source.values.title?.trim()
    const isMovie = source.values.media_type === 'movie'
    return {
        value: source.id,
        label: mediaTitle || source.label,
        selectedLabel: movieTitle && mediaTitle && !isMovie
            ? `${movieTitle} — ${mediaTitle}`
            : (mediaTitle || source.label),
        group: movieTitle || undefined,
    }
}

export default function TemplateSourceSelect({
    mode,
    sources,
    selectedSource,
    isLoading,
    hasMore,
    hasPrevious = false,
    onChange,
    onSearchChange,
    onLoadMore,
    onLoadPrevious,
}: Props) {
    const sourceReg = useMemo(() => {
        const spec: Record<string, {label: string}> = {}
        const values: string[] = []
        for (const source of sources) {
            spec[source.id] = {label: optionForSource(source, mode).label}
            values.push(source.id)
        }
        return createSelectRegistry('LocalMediaProfileTemplateSource', spec, values)
    }, [mode, sources])
    const optionPresentation = useMemo(
        () => new Map(sources.map((source) => {
            const option = optionForSource(source, mode)
            return [source.id, {selectedLabel: option.selectedLabel, group: option.group}]
        })),
        [mode, sources],
    )
    const selectedOption = useMemo(
        () => selectedSource ? optionForSource(selectedSource, mode) : null,
        [mode, selectedSource],
    )
    const sourcesById = useMemo(
        () => new Map(sources.map((source) => [source.id, source])),
        [sources],
    )

    return (
        <LazySearchSelect
            inputId="template-example-source"
            className="template-source-select"
            registry={sourceReg}
            optionPresentation={optionPresentation}
            value={selectedOption}
            isLoading={isLoading}
            hasMore={hasMore}
            hasPrevious={hasPrevious}
            onChange={(option) => {
                const source = sourcesById.get(option.value)
                if (source) onChange(source)
            }}
            onSearchChange={onSearchChange}
            onLoadMore={onLoadMore}
            onLoadPrevious={onLoadPrevious}
            placeholder="Search media…"
            noOptionsMessage="No matching media found"
            ariaLabel="Example source"
        />
    )
}
