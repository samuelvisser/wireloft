import type {LocalMediaProfileMode} from './LocalMediaProfileForm'

export type OutputTemplateVariable = {
    name: string
    description: string
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
    {name: 'episode', description: 'Episode URL slug'},
    {name: 'episode_title', description: 'Episode title'},
    {name: 'title', description: 'Episode title'},
    {name: 'episode_type', description: 'Episode type'},
    {name: 'episode_number', description: 'Episode number'},
    {name: 'ep_id', description: 'Full episode identifier'},
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
    {name: 'movie_dw_id', description: 'Parent movie Daily Wire ID'},
    {name: 'dw_id', description: 'Downloaded item Daily Wire ID'},
    {name: 'movie_author', description: 'Parent movie author or host'},
    {name: 'author', description: 'Downloaded item author'},
    {name: 'movie_mature_rating', description: 'Parent movie rating'},
    {name: 'mature_rating', description: 'Downloaded item rating'},
    {name: 'movie_duration_seconds', description: 'Parent movie runtime in seconds'},
    {name: 'duration_seconds', description: 'Downloaded item runtime in seconds'},
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

export function getOutputTemplateVariables(mode: LocalMediaProfileMode): readonly OutputTemplateVariable[] {
    return mode === 'movie' ? MOVIE_VARIABLES : SHOW_VARIABLES
}
