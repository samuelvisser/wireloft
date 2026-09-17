import {useEffect, useMemo, useRef, useState} from 'react'
import {zodResolver} from '@hookform/resolvers/zod'
import {useQueryClient} from '@tanstack/react-query'
import {useForm} from 'react-hook-form'
import {useNavigate, useParams} from 'react-router-dom'
import {z} from 'zod'

import CustomMetadataEditor from '../../components/CustomMetadataEditor/CustomMetadataEditor'
import {useMovies} from '../../lib/queries'
import {MovieUpdateSchema} from '../../types/schemas/movie'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'

const MovieEditSchema = z.object({
    title: z.string().trim().min(1, 'Movie name is required'),
    producer: z.string().trim(),
})

type MovieEditValues = z.infer<typeof MovieEditSchema>

export default function EditMoviePage() {
    const {slug} = useParams<{slug: string}>()
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const {data: movies, error: moviesError} = useMovies()
    const movie = useMemo(
        () => movies?.find((item) => item.slug === slug),
        [movies, slug],
    )
    const initializedSlug = useRef<string | undefined>(undefined)
    const [metadataOpen, setMetadataOpen] = useState(false)
    const form = useForm<MovieEditValues>({
        resolver: zodResolver(MovieEditSchema),
        defaultValues: {
            title: '',
            producer: '',
        },
        shouldFocusError: true,
    })
    const {reset} = form

    useEffect(() => {
        if (!movie || !slug || initializedSlug.current === slug) return
        initializedSlug.current = slug
        reset({
            title: movie.title,
            producer: movie.authorName ?? '',
        })
    }, [movie, reset, slug])

    const onSubmit = buildServerAwareSubmit<MovieEditValues>(
        form,
        async (values) => {
            if (!movie || !slug) return

            const payload = MovieUpdateSchema.parse({
                ...movie,
                title: values.title,
                authorName: values.producer || null,
            })

            return fetch(`${(window as any).appConfig.API_URL}/movies/${encodeURIComponent(slug)}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify(payload),
            })
        },
        {
            onSuccess: async () => {
                await queryClient.invalidateQueries({queryKey: ['movies']})
                navigate(`/movie/${encodeURIComponent(slug ?? '')}`)
            },
            fieldAlias: {
                authorName: 'producer',
                author_name: 'producer',
            },
            genericMessage: 'Could not save movie',
        },
    )

    const {
        register,
        formState: {errors, isSubmitting},
    } = form

    if (!slug) {
        return (
            <section className="view" aria-labelledby="edit-movie-title">
                <div className="view-header">
                    <h1 id="edit-movie-title">Edit movie</h1>
                </div>
                <p>Movie not found.</p>
                <div className="actions" style={{marginTop: 12}}>
                    <button type="button" className="btn" onClick={() => navigate('/library?type=movies')}>Back</button>
                </div>
            </section>
        )
    }

    if (!movies && !moviesError) {
        return <section className="view"><p>Loading movie…</p></section>
    }

    if (moviesError || !movie) {
        return (
            <section className="view" aria-labelledby="edit-movie-title">
                <div className="view-header">
                    <h1 id="edit-movie-title">Edit movie</h1>
                </div>
                <div className="form-error-card" role="alert">
                    Could not load this movie: {moviesError?.message || 'Movie not found'}
                </div>
                <div className="actions" style={{marginTop: 12}}>
                    <button type="button" className="btn" onClick={() => navigate('/library?type=movies')}>Back</button>
                </div>
            </section>
        )
    }

    return (
        <section className="view" aria-labelledby="edit-movie-title">
            <div className="view-header">
                <h1 id="edit-movie-title">Edit movie</h1>
                <button type="button" className="btn" onClick={() => setMetadataOpen(true)}>
                    Custom metadata
                </button>
            </div>

            <form className="form" onSubmit={onSubmit} noValidate>
                {errors.root && (
                    <div className="form-error-card" role="alert" aria-live="polite">
                        {String(errors.root.message)}
                    </div>
                )}

                <div className="form-row">
                    <label htmlFor="movie-title">Name</label>
                    <input
                        id="movie-title"
                        className="input"
                        type="text"
                        autoFocus
                        aria-invalid={Boolean(errors.title)}
                        aria-describedby={errors.title ? 'movie-title-error' : undefined}
                        {...register('title')}
                    />
                    {errors.title && (
                        <div id="movie-title-error" className="error" role="alert" aria-live="polite">
                            {String(errors.title.message)}
                        </div>
                    )}
                </div>

                <div className="form-row">
                    <label htmlFor="movie-producer">Producer</label>
                    <input
                        id="movie-producer"
                        className="input"
                        type="text"
                        aria-invalid={Boolean(errors.producer)}
                        aria-describedby={errors.producer ? 'movie-producer-error' : undefined}
                        {...register('producer')}
                    />
                    {errors.producer && (
                        <div id="movie-producer-error" className="error" role="alert" aria-live="polite">
                            {String(errors.producer.message)}
                        </div>
                    )}
                </div>

                <div className="actions">
                    <button
                        type="button"
                        className="btn"
                        onClick={() => navigate(`/movie/${encodeURIComponent(slug)}`)}
                        disabled={isSubmitting}
                    >
                        Cancel
                    </button>
                    <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                        {isSubmitting ? 'Saving…' : 'Save changes'}
                    </button>
                </div>
            </form>

            <CustomMetadataEditor
                open={metadataOpen}
                title="Movie custom metadata"
                scope="movie"
                metadata={movie.customMetadata ?? {}}
                endpoint={`/movies/${encodeURIComponent(slug)}/metadata`}
                invalidateQueryKeys={[
                    ['movies'],
                ]}
                onDismiss={() => setMetadataOpen(false)}
            />
        </section>
    )
}
