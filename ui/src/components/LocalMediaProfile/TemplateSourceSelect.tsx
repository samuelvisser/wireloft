import {useMemo} from 'react'

import LazySearchSelect, {
    type LazySearchSelectOption,
} from '../common/LazySearchSelect'
import type {
    LocalMediaProfileTemplateSource,
    LocalMediaProfileTemplateSourceMode,
} from '../../lib/localMediaProfileTemplateSources'
import './TemplateSourceSelect.css'

type Props = {
    mode: LocalMediaProfileTemplateSourceMode
    sources: LocalMediaProfileTemplateSource[]
    selectedSource: LocalMediaProfileTemplateSource | null
    isLoading: boolean
    hasMore: boolean
    onChange: (source: LocalMediaProfileTemplateSource) => void
    onSearchChange: (search: string) => void
    onLoadMore: () => void
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
    onChange,
    onSearchChange,
    onLoadMore,
}: Props) {
    const options = useMemo(
        () => sources.map((source) => optionForSource(source, mode)),
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
            options={options}
            value={selectedOption}
            isLoading={isLoading}
            hasMore={hasMore}
            onChange={(option) => {
                const source = sourcesById.get(option.value)
                if (source) onChange(source)
            }}
            onSearchChange={onSearchChange}
            onLoadMore={onLoadMore}
            placeholder="Search media…"
            noOptionsMessage="No matching media found"
            ariaLabel="Example source"
        />
    )
}
