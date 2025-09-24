import {useEffect, useRef, useState} from 'react'
import {getCurrentAppVersion} from '../../utils/helpers'
import ChooseShowStep from './ChooseShowStep'
import MediaProfileStep from './MediaProfileStep'
import DownloadProfileStep from './DownloadProfileStep'

import type {Versioned} from '../../types/data'
import {ShowCreatePayloadOut, ShowCreatePayloadIn, ShowCreatePayloadSchema} from "../../types/schemas/show";
import {getZodDefaults} from "../../utils/defaultZod";
import {
    DownloadProfilePodcastWithProfilesSchema,
    DownloadProfileSeriesWithProfilesSchema, DownloadProfileUnifiedCreateIn, DownloadProfileUnifiedCreateOut,
    MediaProfileCreateUnionSchema,
    MediaProfileUpsertIn,
    MediaProfileUpsertOut,
} from "../../types/schemas/show_with_profiles";
import {ShowTypeReg} from "../../types/show";

export type Props = {
    onCancel: () => void
}

// Wizard state persistence
const STORAGE_KEY = 'addShowWizardV5'

type WizardType = 'ERROR' | 'INFO'
type WizardMessage = { text: string; type: WizardType }

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
            input: Partial<DownloadProfileUnifiedCreateIn>,
            submit: DownloadProfileUnifiedCreateOut | undefined,
        },
        series: {
            input: Partial<DownloadProfileUnifiedCreateIn>,
            submit: DownloadProfileUnifiedCreateOut | undefined,
        }
    }
    dwSeasons?: { slug: string; name: string }[]
    globalMessage?: WizardMessage | null
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
    // Reusable wizard message helpers
    const [globalMessage, setGlobalMessage] = useState<WizardMessage | null>(() => {
        const ws = loadWizardState() as any
        if (ws?.globalMessage) return ws.globalMessage as WizardMessage
        if (ws?.globalError) return { text: ws.globalError as string, type: 'ERROR' as WizardType }
        return null
    })
    const setWizardMessage = (message: string, type: WizardType) => {
        setGlobalMessage({ text: message, type })
    }
    const clearWizardMessage = () => setGlobalMessage(null)
    // Wizard step: 1 = URL, 2 = Media Profile, 3 = Show
    const [step, setStep] = useState<1 | 2 | 3>(() => loadWizardState()?.step ?? 1)

    const [showInput, setShowInput] = useState<Partial<ShowCreatePayloadIn>>(
        () => loadWizardState()?.show.input ?? getZodDefaults(ShowCreatePayloadSchema))
    const [showSubmit, setShowSubmit] = useState<ShowCreatePayloadOut | undefined>(() => loadWizardState()?.show.submit)

    const [mediaProfileInput, setMediaProfileInput] = useState<Partial<MediaProfileUpsertIn>>(
        () => loadWizardState()?.mediaProfile.input ?? getZodDefaults(MediaProfileCreateUnionSchema))
    const [mediaProfileSubmit, setMediaProfileSubmit] = useState<MediaProfileUpsertOut | undefined>(() => loadWizardState()?.mediaProfile.submit)

    const [downloadProfilePodcastInput, setDownloadProfilePodcastInput] = useState<Partial<DownloadProfileUnifiedCreateIn>>(
        () => loadWizardState()?.downloadProfile.podcast.input ?? getZodDefaults(DownloadProfilePodcastWithProfilesSchema))
    const [downloadProfilePodcastSubmit, setDownloadProfilePodcastSubmit] = useState<DownloadProfileUnifiedCreateOut | undefined>(() => loadWizardState()?.downloadProfile.podcast.submit)

    const [downloadProfileSeriesInput, setDownloadProfileSeriesInput] = useState<Partial<DownloadProfileUnifiedCreateIn>>(
        () => loadWizardState()?.downloadProfile.series.input ?? getZodDefaults(DownloadProfileSeriesWithProfilesSchema))
    const [downloadProfileSeriesSubmit, setDownloadProfileSeriesSubmit] = useState<DownloadProfileUnifiedCreateOut | undefined>(() => loadWizardState()?.downloadProfile.series.submit)

    // Refs to avoid stale state during immediate Finish after submit
    const downloadProfilePodcastSubmitRef = useRef(downloadProfilePodcastSubmit)
    const downloadProfileSeriesSubmitRef = useRef(downloadProfileSeriesSubmit)

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
            globalMessage,
        })
    }, [step, showInput, showSubmit, mediaProfileInput, mediaProfileSubmit, downloadProfilePodcastInput, downloadProfilePodcastSubmit, downloadProfileSeriesInput, downloadProfileSeriesSubmit, dwSeasons, globalMessage])

    function handleCancel() {
        clearWizardState()
        onCancel()
    }

    async function handleFinish() {
        // Build payload from current in-memory state to avoid race with async persistence
        console.log('handleFinish')

        const show = showSubmit
        const mediaProfile = mediaProfileSubmit

        if (!show) {
            setWizardMessage('Please complete the "Choose show" step before finishing.', 'ERROR')
            return
        }
        if (!mediaProfile) {
            setWizardMessage('Please complete the Media Profile step before finishing.', 'ERROR')
            return
        }

        let downloadProfile;
        if(show.type === ShowTypeReg.Enum.podcast) {
            downloadProfile = downloadProfilePodcastSubmitRef.current ?? downloadProfilePodcastSubmit
        } else if(show.type === ShowTypeReg.Enum.series) {
            downloadProfile = downloadProfileSeriesSubmitRef.current ?? downloadProfileSeriesSubmit
        }
        if (!downloadProfile) {
            setWizardMessage('Please complete the Download Profile step before finishing.', 'ERROR')
            return
        }
        setWizardMessage('Validating...', 'INFO')

        console.log('handleFinish', show, mediaProfile, downloadProfile)

        console.log(JSON.stringify({
                show,
                mediaProfile,
                downloadProfile
            }))




        const result = fetch(`${(window as any).appConfig.API_URL}/shows/with-profiles`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                show,
                mediaProfile,
                downloadProfile
            }),
        })

        console.log('queryResult', result)


        result.then(() => {
            clearWizardMessage()
        })


        // TODO finish and navigate to home
        // await qc.invalidateQueries({queryKey: ['mediaProfiles']})
        // await qc.invalidateQueries({queryKey: ['shows']})
        // clearWizardState()
        // onCancel()
    }

    return (
        <div>
            {globalMessage && (
                <div
                    className={globalMessage.type === 'ERROR' ? 'form-error-card' : 'form-info-card'}
                    role="alert"
                    aria-live="polite"
                    style={{marginBottom: 12}}
                >
                    {globalMessage.text}
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
                        podcast: (v) => {
                            setDownloadProfilePodcastSubmit(v)
                            downloadProfilePodcastSubmitRef.current = v
                        },
                        series: (v) => {
                            setDownloadProfileSeriesSubmit(v)
                            downloadProfileSeriesSubmitRef.current = v
                        },
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
