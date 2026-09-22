import type {LocalMediaProfileMode} from './LocalMediaProfileForm'

export type OutputTemplateVariableReadMore = {
    summary?: string
    paragraphs: readonly string[]
}

export type OutputTemplateVariable = {
    name: string
    description: string
    readMore?: OutputTemplateVariableReadMore
}

const DATE_VARIABLES: readonly OutputTemplateVariable[] = [
    {name: 'date', description: 'Date as YYYY-MM-DD'},
    {name: 'time', description: 'Time as HH:MM:SS'},
    {name: 'datetime', description: 'Date and time'},
    {name: 'year', description: 'Four-digit year'},
    {name: 'month', description: 'Two-digit month'},
    {name: 'day', description: 'Two-digit day'},
    {name: 'hour', description: 'Two-digit hour'},
    {name: 'minute', description: 'Two-digit minute'},
    {name: 'second', description: 'Two-digit second'},
]

const SHOW_VARIABLES: readonly OutputTemplateVariable[] = [
    {name: 'show', description: 'Show URL slug'},
    {name: 'show_title', description: 'Show title'},
    {name: 'season', description: 'Season URL slug'},
    {name: 'season_name', description: 'Season name'},
    {name: 'season_index', description: 'WireLoft internal season index'},
    {
        name: 'season_type',
        description: 'Season type: normal or extra',
        readMore: {
            paragraphs: [
                'WireLoft attempts to classify whether a season is regular or extra based on it\'s title.' +
                'Use this value in Jinja conditions when normal and extra seasons need different paths.',
                '<strong>normal</strong> season contains regular show episodes',
                '<strong>extra</strong> season contains extra\'s for the show'
            ],
        },
    },
    {
        name: 'season_number',
        description: 'Stable media season number; Extras seasons use 0',
        readMore: {
            paragraphs: [
                'Normal seasons use their stable media-facing season number, while every extras season uses 0.',
                'Unlike the internal season_index, this value is designed for media-server paths and is not affected by where extras seasons appear in The Daily Wire season list.',
            ],
        },
    },
    {name: 'episode', description: 'Episode URL slug'},
    {name: 'episode_title', description: 'Episode title'},
    {name: 'title', description: 'Episode title'},
    {name: 'dw_episode_number', description: 'Raw episode number exactly as returned by The Daily Wire'},
    {name: 'episode_type', description: 'Episode type: ep, ep-extra, aux, or trailer'},
    {name: 'episode_extra_type', description: 'Episode-extra subtype: other or trailer; empty otherwise'},
    {name: 'episode_number', description: 'Main episode number, or WireLoft counter for aux/trailer'},
    {name: 'episode_sub_number', description: 'The Daily Wire sub-episode number for episode extras; empty otherwise'},
    {name: 'episode_label', description: 'Canonical label without the type prefix (e.g. 2497, 2497.1, S01E07, S01E07.1)'},
    {name: 'episode_identifier', description: 'Full WireLoft episode identifier including the type prefix; guaranteed unique within the show'},
    {name: 'episode_published_date', description: 'Published date as YYYY-MM-DD'},
    {name: 'episode_published_time', description: 'Published time as HH:MM:SS'},
    {name: 'episode_published_datetime', description: 'Published date and time'},
    ...DATE_VARIABLES,
]

const MOVIE_VARIABLES: readonly OutputTemplateVariable[] = [
    {name: 'movie_slug', description: 'Parent movie URL slug'},
    {name: 'slug', description: 'Downloaded item URL slug'},
    {name: 'movie_title', description: 'Parent movie title'},
    {name: 'title', description: 'Downloaded item title'},
    {name: 'movie_extended_title', description: 'Parent movie full title'},
    {name: 'extended_title', description: 'Downloaded item full title'},
    {name: 'movie_author', description: 'Parent movie author or host'},
    {name: 'author', description: 'Downloaded item author'},
    {name: 'movie_mature_rating', description: 'Parent movie rating'},
    {name: 'mature_rating', description: 'Downloaded item rating'},
    {name: 'movie_duration_seconds', description: 'Parent movie runtime in seconds'},
    {name: 'duration_seconds', description: 'Downloaded item duration'},
    {name: 'rating', description: 'Downloaded item rating'},
    {name: 'media_type', description: 'movie, trailer, interview, or another extra type'},
    {name: 'movie_date', description: 'Parent movie release date as YYYY-MM-DD'},
    {name: 'date', description: 'Downloaded item date as YYYY-MM-DD'},
    {name: 'movie_time', description: 'Parent movie release time as HH:MM:SS'},
    {name: 'time', description: 'Downloaded item time as HH:MM:SS'},
    {name: 'movie_datetime', description: 'Parent movie release date and time'},
    {name: 'datetime', description: 'Downloaded item date and time'},
    {name: 'movie_year', description: 'Parent movie release year'},
    {name: 'year', description: 'Downloaded item year'},
    {name: 'movie_month', description: 'Parent movie release month'},
    {name: 'month', description: 'Downloaded item month'},
    {name: 'movie_day', description: 'Parent movie release day'},
    {name: 'day', description: 'Downloaded item day'},
    {name: 'movie_hour', description: 'Parent movie release hour'},
    {name: 'hour', description: 'Downloaded item hour'},
    {name: 'movie_minute', description: 'Parent movie release minute'},
    {name: 'minute', description: 'Downloaded item minute'},
    {name: 'movie_second', description: 'Parent movie release second'},
    {name: 'second', description: 'Downloaded item second'},
]

export function getOutputTemplateVariables(
    mode: LocalMediaProfileMode,
    customVariables: readonly OutputTemplateVariable[] = [],
): readonly OutputTemplateVariable[] {
    const baseVariables = mode === 'movie' ? MOVIE_VARIABLES : SHOW_VARIABLES
    const merged = new Map(baseVariables.map((variable) => [variable.name, variable]))
    for (const variable of customVariables) merged.set(variable.name, variable)
    return [...merged.values()]
}
