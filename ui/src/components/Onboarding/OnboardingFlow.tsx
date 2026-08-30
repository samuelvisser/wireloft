import {useCallback, useEffect, useRef, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Route, Routes, useNavigate} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import AddShowPage from '../AddShowPage/AddShowPage'
import DailywireAuthCard from '../DailywireAuth/DailywireAuthCard'
import BrowsePage from '../../pages/BrowsePage'
import MoviePage from '../../pages/movie/MoviePage'
import {useMovies} from '../../lib/queries'
import {DailywireCatalogMovieRead, DailywireCatalogShowRead} from '../../types/schemas/dailywire_catalog'
import {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'
import {ShowRead} from '../../types/schemas/show'
import OnboardingMovieProfileStep from './OnboardingMovieProfileStep'
import './Onboarding.css'


type OnboardingStep = 'welcome' | 'dailywire' | 'security' | 'browse' | 'show' | 'movie-profile' | 'movie'

type Props = {
    adminPasswordConfigured: boolean
    onComplete: () => void
}

const STEP_LABELS = ['Welcome', 'Daily Wire', 'Security', 'First media']

function visibleStepIndex(step: OnboardingStep) {
    if (step === 'welcome') return 0
    if (step === 'dailywire') return 1
    if (step === 'security') return 2
    return 3
}

export default function OnboardingFlow({adminPasswordConfigured, onComplete}: Props) {
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const {data: localMovies} = useMovies()
    const [step, setStep] = useState<OnboardingStep>('welcome')
    const [dailyWireConnected, setDailyWireConnected] = useState<boolean | null>(null)
    const [selectedShow, setSelectedShow] = useState<DailywireCatalogShowRead | null>(null)
    const [selectedShowWasPresent, setSelectedShowWasPresent] = useState(false)
    const [selectedMovie, setSelectedMovie] = useState<DailywireCatalogMovieRead | null>(null)
    const [movieProfile, setMovieProfile] = useState<LocalMediaProfileRead | null>(null)
    const [isCompleting, setIsCompleting] = useState(false)
    const completingRef = useRef(false)
    const [error, setError] = useState<string | null>(null)

    const completeOnboarding = useCallback(async () => {
        if (completingRef.current) return
        completingRef.current = true
        setIsCompleting(true)
        setError(null)
        try {
            const response = await fetch(`${(window as any).appConfig.API_URL}/onboarding/complete`, {
                method: 'POST',
                credentials: 'include',
            })
            if (!response.ok) throw new Error(`HTTP ${response.status}`)
            onComplete()
        } catch {
            setError('WireLoft could not finish onboarding. Please try again.')
        } finally {
            completingRef.current = false
            setIsCompleting(false)
        }
    }, [onComplete])

    useEffect(() => {
        if (step !== 'dailywire') return
        let cancelled = false

        const refresh = async () => {
            try {
                const base = (window as any).appConfig.API_URL?.replace(/\/+$/, '')
                const response = await fetch(`${base}/dailywire/auth/status`, {credentials: 'include'})
                if (!response.ok) return
                const status = await response.json()
                if (!cancelled) setDailyWireConnected(Boolean(status?.authenticated))
            } catch {
                if (!cancelled) setDailyWireConnected(false)
            }
        }

        void refresh()
        const timer = window.setInterval(() => void refresh(), 2_000)
        return () => {
            cancelled = true
            window.clearInterval(timer)
        }
    }, [step])

    const selectShow = (show: DailywireCatalogShowRead) => {
        const currentShows = queryClient.getQueryData<ShowRead[]>(['shows']) ?? []
        setSelectedShowWasPresent(currentShows.some((item) => item.slug === show.slug))
        setSelectedShow(show)
        setError(null)
        setStep('show')
    }

    const leaveShowWizard = async () => {
        try {
            const response = await fetch(`${(window as any).appConfig.API_URL}/shows`, {credentials: 'include'})
            if (response.ok) {
                const currentShows = await response.json() as ShowRead[]
                queryClient.setQueryData(['shows'], currentShows)
                const wasAdded = !selectedShowWasPresent && currentShows.some((item) => item.slug === selectedShow?.slug)
                if (wasAdded) {
                    await completeOnboarding()
                    return
                }
            }
        } catch {
            // Returning to browse still gives the user a safe way to finish or retry setup.
        }
        setStep('browse')
    }

    const selectMovie = (movie: DailywireCatalogMovieRead) => {
        setSelectedMovie(movie)
        setMovieProfile(null)
        setError(null)
        setStep('movie-profile')
    }

    useEffect(() => {
        if (step !== 'movie' || !selectedMovie) return
        if (localMovies?.some((movie) => movie.slug === selectedMovie.slug)) {
            void completeOnboarding()
        }
    }, [completeOnboarding, localMovies, selectedMovie, step])

    const progress = visibleStepIndex(step)
    const showTopbar = step !== 'welcome'

    return (
        <div className={`onboarding-shell onboarding-step-${step}`}>
            <div className="onboarding-backdrop" aria-hidden="true"/>

            {showTopbar && (
                <header className="onboarding-topbar">
                    <img src="/logo-wide-full.png" alt="WireLoft"/>
                    <ol className="onboarding-progress" aria-label="Onboarding progress">
                        {STEP_LABELS.map((label, index) => (
                            <li key={label} className={index === progress ? 'is-active' : index < progress ? 'is-complete' : ''}>
                                <span>{index < progress ? <FontAwesomeIcon icon={['fas', 'check']}/> : index + 1}</span>
                                <small>{label}</small>
                            </li>
                        ))}
                    </ol>
                </header>
            )}

            {error && (
                <div className="onboarding-global-error form-error-card" role="alert">
                    <span>{error}</span>
                    <button className="btn" type="button" onClick={() => void completeOnboarding()} disabled={isCompleting}>
                        Try again
                    </button>
                </div>
            )}

            {step === 'welcome' && (
                <main className="onboarding-welcome">
                    <div className="onboarding-welcome-glow" aria-hidden="true"/>
                    <img className="onboarding-welcome-logo" src="/logo-wide-full.png" alt="WireLoft"/>
                    <p>Bring your Daily Wire library home.</p>
                    <button className="btn btn-primary onboarding-primary-action" type="button" onClick={() => setStep('dailywire')}>
                        Continue
                        <FontAwesomeIcon icon={['fas', 'arrow-right']}/>
                    </button>
                </main>
            )}

            {step === 'dailywire' && (
                <main className="onboarding-stage onboarding-stage-narrow">
                    <div className="onboarding-section-heading">
                        <span className="onboarding-eyebrow">Daily Wire account</span>
                        <h1>Connect your subscription</h1>
                        <p>
                            Sign in through Daily Wire's device authorization flow to access content included with your
                            membership. WireLoft never asks for or stores your Daily Wire password.
                        </p>
                    </div>
                    <DailywireAuthCard/>
                    <div className="onboarding-stage-actions">
                        <button className="btn" type="button" onClick={() => setStep('welcome')}>Back</button>
                        {dailyWireConnected ? (
                            <button className="btn btn-primary" type="button" onClick={() => setStep('security')}>
                                Continue
                            </button>
                        ) : (
                            <button className="btn" type="button" onClick={() => setStep('security')}>
                                Skip for now
                            </button>
                        )}
                    </div>
                </main>
            )}

            {step === 'security' && (
                <main className="onboarding-stage onboarding-stage-narrow">
                    <div className="onboarding-section-heading">
                        <span className="onboarding-eyebrow">Protect WireLoft</span>
                        <h1>Create an administrator password</h1>
                        <p>
                            Set the environment variable below on your WireLoft container and restart it. This is
                            especially important when WireLoft is reachable through a reverse proxy.
                        </p>
                    </div>

                    <div className={`onboarding-security-card${adminPasswordConfigured ? ' is-configured' : ''}`}>
                        <div className="onboarding-security-icon" aria-hidden="true">
                            {adminPasswordConfigured
                                ? <FontAwesomeIcon icon={['fas', 'shield-halved']}/>
                                : <FontAwesomeIcon icon={['fas', 'triangle-exclamation']}/>}
                        </div>
                        <div>
                            <strong>{adminPasswordConfigured ? 'Administrator authentication is configured' : 'Administrator authentication is not configured yet'}</strong>
                            <p>
                                {adminPasswordConfigured
                                    ? 'WireLoft will require the administrator password before showing protected pages.'
                                    : 'Without this value, anyone who can reach WireLoft can control it and access its stored account session.'}
                            </p>
                        </div>
                    </div>

                    <div className="onboarding-env-example">
                        <div>
                            <span>Environment variable</span>
                            <code>WL_ADMIN_AUTH__PASSWORD</code>
                        </div>
                        <pre><code>{'environment:\n  WL_ADMIN_AUTH__PASSWORD: "choose-a-long-unique-password"'}</code></pre>
                    </div>

                    <p className="onboarding-security-note">
                        A restart is required after changing the variable. On the next visit, WireLoft will show its own
                        administrator login before loading the application.
                    </p>

                    <div className="onboarding-stage-actions">
                        <button className="btn" type="button" onClick={() => setStep('dailywire')}>Back</button>
                        <button className="btn btn-primary" type="button" onClick={() => setStep('browse')}>
                            Continue to library setup
                        </button>
                    </div>
                </main>
            )}

            {step === 'browse' && (
                <main className="onboarding-stage onboarding-stage-wide">
                    <BrowsePage
                        onboarding
                        onShowSelect={selectShow}
                        onMovieSelect={selectMovie}
                        onSkip={() => void completeOnboarding()}
                    />
                    {isCompleting && <div className="onboarding-completing" role="status">Finishing setup…</div>}
                </main>
            )}

            {step === 'show' && selectedShow && (
                <main className="onboarding-stage onboarding-stage-wide onboarding-wizard-stage">
                    <div className="onboarding-section-heading onboarding-nested-heading">
                        <span className="onboarding-eyebrow">Add your first show</span>
                        <h1>{selectedShow.title}</h1>
                        <p>The normal Add Show wizard will let you confirm a Local Media Profile before any downloads are configured.</p>
                    </div>
                    <AddShowPage
                        initialUrl={`https://www.dailywire.com/show/${selectedShow.slug}`}
                        onCancel={() => void leaveShowWizard()}
                    />
                </main>
            )}

            {step === 'movie-profile' && selectedMovie && (
                <main className="onboarding-stage onboarding-stage-wide">
                    <OnboardingMovieProfileStep
                        movieTitle={selectedMovie.title}
                        onBack={() => {
                            navigate('/?type=movies', {replace: true})
                            setStep('browse')
                        }}
                        onContinue={(profile) => {
                            queryClient.setQueryData<LocalMediaProfileRead[]>(['localMediaProfiles'], (current) => {
                                const remaining = (current ?? []).filter((item) => item.id !== profile.id)
                                return [profile, ...remaining]
                            })
                            setMovieProfile(profile)
                            navigate(`/movie/${selectedMovie.slug}`, {replace: true})
                            setStep('movie')
                        }}
                    />
                </main>
            )}

            {step === 'movie' && selectedMovie && movieProfile && (
                <main className="onboarding-stage onboarding-stage-movie">
                    <button
                        className="btn onboarding-movie-back"
                        type="button"
                        onClick={() => setStep('movie-profile')}
                    >
                        <FontAwesomeIcon icon={['fas', 'arrow-left']}/> Back to profile
                    </button>
                    <Routes>
                        <Route path="/movie/:slug" element={<MoviePage/>}/>
                    </Routes>
                    {isCompleting && <div className="onboarding-completing" role="status">Finishing setup…</div>}
                </main>
            )}
        </div>
    )
}
