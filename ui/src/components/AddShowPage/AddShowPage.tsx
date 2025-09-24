import {useEffect, useState} from 'react'
import {getCurrentAppVersion} from '../../utils/helpers'
import ChooseShowStep from './ChooseShowStep'
import MediaProfileStep from './MediaProfileStep'
import DownloadProfileStep from './DownloadProfileStep'

import type {Versioned} from '../../types/data'
import {ShowCreatePayloadOut, ShowCreatePayloadIn, ShowCreatePayloadSchema} from "../../types/schemas/show";
import {getZodDefaults} from "../../utils/defaultZod";
import {
    DownloadProfilePodcastWithProfilesIn, DownloadProfilePodcastWithProfilesOut,
    DownloadProfilePodcastWithProfilesSchema,
    MediaProfileUpsertIn,
    MediaProfileUpsertOut,
    MediaProfileUpsertSchema
} from "../../types/schemas/show_with_profiles";
import {ShowTypeReg} from "../../types/show";
import {
    DownloadProfileSeriesCreateIn,
    DownloadProfileSeriesCreateOut, DownloadProfileSeriesCreateSchema
} from "../../types/schemas/download_profile_series";

export type Props = {
    onCancel: () => void
}

// Wizard state persistence
const STORAGE_KEY = 'addShowWizardV5'

type WizardState = {
    step: 1 | 2 | 3
    show: {
        input: Partial<ShowCreatePayloadIn>,
        submit: ShowCreatePayloadOut | undefined,
    },
    mediaProfile: {
        input: Partial<MediaProfileUpsertIn>,
        submit: MediaProfileUpsertOut | undefined,
    },
    downloadProfile: {
        podcast: {
            input: Partial<DownloadProfilePodcastWithProfilesIn>,
            submit: DownloadProfilePodcastWithProfilesOut | undefined,
        },
        series: {
            input: Partial<DownloadProfileSeriesCreateIn>,
            submit: DownloadProfileSeriesCreateOut | undefined,
        }
    }
    dwSeasons?: { slug: string; name: string }[]
    globalError?: string | null
}

function loadWizardState(): WizardState | null {
    try {
        const raw = localStorage.getItem(STORAGE_KEY)
        if (!raw) return null
        const parsed = JSON.parse(raw) as any
        const current = getCurrentAppVersion()
        // New format { version, data }
        if (parsed && typeof parsed === 'object' && 'version' in parsed && 'data' in parsed) {
            if (typeof current === 'string') {
                if (parsed.version === current) {
                    return parsed.data as WizardState
                } else {
                    // Version mismatch: clear and invalidate
                    localStorage.removeItem(STORAGE_KEY)
                    return null
                }
            } else {
                // Current version unknown: don't use, but also don't clear
                return null
            }
        }
        // Legacy format (no version): only invalidate if we know current version
        if (typeof current === 'string') {
            localStorage.removeItem(STORAGE_KEY)
        }
        return null
    } catch {
        return null
    }
}

function saveWizardState(state: WizardState) {
    try {
        const ver = getCurrentAppVersion()
        if (!ver) {
            // If the version is unknown, don't persist to avoid a stale format
            return
        }
        const payload: Versioned<WizardState> = {version: ver, data: state}
        localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
        // ignore write errors (quota, etc.)
    }
}

function clearWizardState() {
    try {
        localStorage.removeItem(STORAGE_KEY)
    } catch {
        // ignore
    }
}

export default function AddShowPage({onCancel}: Props) {
    // Reusable wizard error helpers
    const [globalError, setGlobalError] = useState<string | null>(() => loadWizardState()?.globalError ?? null)
    const setWizardError = (message: string) => {
        setGlobalError(message)
    }
    const clearWizardError = () => setGlobalError(null)
    // Wizard step: 1 = URL, 2 = Media Profile, 3 = Show
    const [step, setStep] = useState<1 | 2 | 3>(() => loadWizardState()?.step ?? 1)

    const [showInput, setShowInput] = useState<Partial<ShowCreatePayloadIn>>(
        () => loadWizardState()?.show.input ?? getZodDefaults(ShowCreatePayloadSchema))
    const [showSubmit, setShowSubmit] = useState<ShowCreatePayloadOut | undefined>(() => loadWizardState()?.show.submit)

    const [mediaProfileInput, setMediaProfileInput] = useState<Partial<MediaProfileUpsertIn>>(
        () => loadWizardState()?.mediaProfile.input ?? getZodDefaults(MediaProfileUpsertSchema))
    const [mediaProfileSubmit, setMediaProfileSubmit] = useState<MediaProfileUpsertOut | undefined>(() => loadWizardState()?.mediaProfile.submit)

    const [downloadProfilePodcastInput, setDownloadProfilePodcastInput] = useState<Partial<DownloadProfilePodcastWithProfilesIn>>(
        () => loadWizardState()?.downloadProfile.podcast.input ?? getZodDefaults(DownloadProfilePodcastWithProfilesSchema))
    const [downloadProfilePodcastSubmit, setDownloadProfilePodcastSubmit] = useState<DownloadProfilePodcastWithProfilesOut | undefined>(() => loadWizardState()?.downloadProfile.podcast.submit)

    const [downloadProfileSeriesInput, setDownloadProfileSeriesInput] = useState<Partial<DownloadProfileSeriesCreateIn>>(
        () => loadWizardState()?.downloadProfile.series.input ?? getZodDefaults(DownloadProfileSeriesCreateSchema))
    const [downloadProfileSeriesSubmit, setDownloadProfileSeriesSubmit] = useState<DownloadProfileSeriesCreateOut | undefined>(() => loadWizardState()?.downloadProfile.series.submit)

    const [dwSeasons, setDwSeasons] = useState<{ slug: string; name: string }[]>(
        () => loadWizardState()?.dwSeasons ?? []
    )

    // Persist wizard state on any change
    useEffect(() => {
        saveWizardState({
            step,
            show: {
                input: showInput,
                submit: showSubmit
            },
            mediaProfile: {
                input: mediaProfileInput,
                submit: mediaProfileSubmit,
            },
            downloadProfile: {
                podcast: {
                    input: downloadProfilePodcastInput,
                    submit: downloadProfilePodcastSubmit
                },
                series: {
                    input: downloadProfileSeriesInput,
                    submit: downloadProfileSeriesSubmit
                }
            },
            dwSeasons,
            globalError,
        })
    }, [step, showInput, showSubmit, mediaProfileInput, mediaProfileSubmit, downloadProfilePodcastInput, downloadProfilePodcastSubmit, downloadProfileSeriesInput, downloadProfileSeriesSubmit, dwSeasons, globalError])

    function handleCancel() {
        clearWizardState()
        onCancel()
    }

    async function handleFinish() {
        // Build payload from wizard state and submit via validated RHF form
        console.log('handleFinish')

        const wizard = loadWizardState();
        console.log('wizard', wizard)
        console.log('podcast', downloadProfilePodcastSubmit)
        if (!wizard) {
            setWizardError('Unexpected error: Wizard state not found. Please restart the wizard.')
            return;
        }
        if (!wizard.show.submit) {
            setWizardError('Please complete the "Choose show" step before finishing.')
            return;
        }
        if (!wizard.mediaProfile.submit) {
            setWizardError('Please complete the Media Profile step before finishing.')
            return;
        }
        if (!wizard.downloadProfile.podcast.submit && !wizard.downloadProfile.series.submit) {
            setWizardError('Please complete the Download Profile step before finishing.')
            return;
        }

        console.log('show root error')
        setWizardError('Validating...')

        // Clear any previous global error now that all validations passed
        // clearWizardError()

        console.log('handleFinish', wizard)

        const downloadProfile = wizard.downloadProfile.podcast.submit
            ? ({...wizard.downloadProfile.podcast.submit, op: 'podcast'} as const)
            : wizard.downloadProfile.series.submit
                ? ({...wizard.downloadProfile.series.submit, op: 'series'} as const)
                : undefined;
        if (!downloadProfile) return;


        // TODO finish and navigate to home
        // await qc.invalidateQueries({queryKey: ['mediaProfiles']})
        // await qc.invalidateQueries({queryKey: ['shows']})
        // clearWizardState()
        // onCancel()
    }

    return (
        <div>
            {globalError && (
                <div className="form-error-card" role="alert" aria-live="polite" style={{marginBottom: 12}}>
                    {globalError}
                </div>
            )}

            <div className="help" aria-live="polite" style={{marginBottom: 12}}>
                Step {step} of 3: {step === 1 ? 'Choose show' : step === 2 ? 'Media Profile' :
                (showSubmit?.type === ShowTypeReg.Enum.podcast ? 'Download Profile for Podcasts' :
                    showSubmit?.type === ShowTypeReg.Enum.series ? 'Download Profile for Series' :
                        'Download Profile')}
            </div>

            {step === 1 && (
                <ChooseShowStep
                    value={showInput}
                    onChange={setShowInput}
                    onSubmit={setShowSubmit}
                    onContinue={() => setStep(2)}
                    onCancel={handleCancel}
                    onDailywireSeasons={setDwSeasons}
                />
            )}

            {step === 2 && (
                <MediaProfileStep
                    value={mediaProfileInput}
                    onChange={setMediaProfileInput}
                    onSubmit={setMediaProfileSubmit}
                    onBack={() => setStep(1)}
                    onContinue={() => setStep(3)}
                    onCancel={handleCancel}
                    showSlug={showSubmit?.slug}
                />
            )}

            {step === 3 && (
                <DownloadProfileStep
                    value={{
                        podcast: downloadProfilePodcastInput,
                        series: downloadProfileSeriesInput,
                    }}
                    onChange={{
                        podcast: setDownloadProfilePodcastInput,
                        series: setDownloadProfileSeriesInput,
                    }}
                    onSubmit={{
                        podcast: setDownloadProfilePodcastSubmit,
                        series: setDownloadProfileSeriesSubmit,
                    }}
                    onBack={() => setStep(2)}
                    onFinish={handleFinish}
                    onCancel={handleCancel}
                    showSlug={showSubmit?.slug}
                    showType={showSubmit?.type}
                    seasons={dwSeasons}
                />
            )}
        </div>
    )
}
