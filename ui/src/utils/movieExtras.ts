import {MovieExtraType} from '../types/schemas/dailywire_catalog'

export const MOVIE_EXTRA_TYPE_LABELS: Record<MovieExtraType, string> = {
    behindthescenes: 'Behind the scenes',
    deleted: 'Deleted scene',
    featurette: 'Featurette',
    interview: 'Interview',
    scene: 'Scene',
    short: 'Short',
    trailer: 'Trailer',
    other: 'Other',
}

export function movieExtraTypeLabel(value: string | null | undefined) {
    return MOVIE_EXTRA_TYPE_LABELS[value as MovieExtraType]
        ?? value?.replace(/_/g, ' ').replace(/^./, (character) => character.toUpperCase())
        ?? 'Movie extra'
}
