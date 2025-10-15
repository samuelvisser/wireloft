import {useEffect, useRef, useState} from 'react'
import {getCurrentAppVersion, getErrorMessageFromResponse} from '../../utils/helpers'
import ChooseShowStep from './ChooseShowStep'
import LocalMediaProfileStep from './LocalMediaProfileStep'
import DownloadProfileStep from './DownloadProfileStep'

import type {Versioned} from '../../types/data'
import {ShowCreatePayloadOut, ShowCreatePayloadIn, ShowCreatePayloadSchema} from "../../types/schemas/show";
import {getZodDefaults} from "../../utils/defaultZod";
import {
    PodcastDownloadProfileBundleSchema,
    SeriesDownloadProfileBundleSchema, DownloadProfileUnifiedCreateIn, DownloadProfileUnifiedCreateOut,
    LocalMediaProfileCreateUnionSchema,
    LocalMediaProfileUpsertIn,
    LocalMediaProfileUpsertOut,
} from "../../types/schemas/show_as_bundle";
import {ShowTypeReg} from "../../types/show";
import {useQueryClient} from "@tanstack/react-query";
import {SeasonDetachedOut} from "../../types/schemas/season";

export type Props = {
    onCancel: () => void
}

// Wizard state persistence
const STORAGE_KEY = 'addShowWizardV7'

type WizardType = 'ERROR' | 'INFO'
type WizardMessage = { text: string; type: WizardType }

type WizardState = {
    step: 1 | 2 | 3
    show: {
        input: Partial<ShowCreatePayloadIn>,
        submit: ShowCreatePayloadOut | undefined,
    },
    localMediaProfile: {
        input: Partial<LocalMediaProfileUpsertIn>,
        submit: LocalMediaProfileUpsertOut | undefined,
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
    seasons: SeasonDetachedOut[] | undefined,
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
        if (ws?.globalError) return {text: ws.globalError as string, type: 'ERROR' as WizardType}
        return null
    })
    const setWizardMessage = (message: string, type: WizardType) => {
        setGlobalMessage({text: message, type})
    }
    const clearWizardMessage = () => setGlobalMessage(null)
    const qc = useQueryClient()

    // Wizard step: 1 = URL, 2 = Media Profile, 3 = Show
    const [step, setStep] = useState<1 | 2 | 3>(() => loadWizardState()?.step ?? 1)

    const [showInput, setShowInput] = useState<Partial<ShowCreatePayloadIn>>(
        () => loadWizardState()?.show.input ?? getZodDefaults(ShowCreatePayloadSchema))
    const [showSubmit, setShowSubmit] = useState<ShowCreatePayloadOut | undefined>(() => loadWizardState()?.show.submit)

    const [localMediaProfileInput, setLocalMediaProfileInput] = useState<Partial<LocalMediaProfileUpsertIn>>(
        () => loadWizardState()?.localMediaProfile.input ?? getZodDefaults(LocalMediaProfileCreateUnionSchema))
    const [localMediaProfileSubmit, setLocalMediaProfileSubmit] = useState<LocalMediaProfileUpsertOut | undefined>(() => loadWizardState()?.localMediaProfile.submit)

    const [downloadProfilePodcastInput, setPodcastDownloadProfileInput] = useState<Partial<DownloadProfileUnifiedCreateIn>>(
        () => loadWizardState()?.downloadProfile.podcast.input ?? getZodDefaults(PodcastDownloadProfileBundleSchema))
    const [downloadProfilePodcastSubmit, setPodcastDownloadProfileSubmit] = useState<DownloadProfileUnifiedCreateOut | undefined>(() => loadWizardState()?.downloadProfile.podcast.submit)

    const [downloadProfileSeriesInput, setSeriesDownloadProfileInput] = useState<Partial<DownloadProfileUnifiedCreateIn>>(
        () => loadWizardState()?.downloadProfile.series.input ?? getZodDefaults(SeriesDownloadProfileBundleSchema))
    const [downloadProfileSeriesSubmit, setSeriesDownloadProfileSubmit] = useState<DownloadProfileUnifiedCreateOut | undefined>(() => loadWizardState()?.downloadProfile.series.submit)

    const [seasonsSubmit, setSeasonsSubmit] = useState<SeasonDetachedOut[] | undefined>(
        () => loadWizardState()?.seasons ?? [])

    // Refs to avoid stale state during immediate Finish after submit
    const downloadProfilePodcastSubmitRef = useRef(downloadProfilePodcastSubmit)
    const downloadProfileSeriesSubmitRef = useRef(downloadProfileSeriesSubmit)

    // Persist wizard state on any change
    useEffect(() => {
        saveWizardState({
            step,
            show: {
                input: showInput,
                submit: showSubmit
            },
            localMediaProfile: {
                input: localMediaProfileInput,
                submit: localMediaProfileSubmit,
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
            seasons: seasonsSubmit,
            globalMessage,
        })
    }, [step, showInput, showSubmit, localMediaProfileInput, localMediaProfileSubmit, downloadProfilePodcastInput, downloadProfilePodcastSubmit, downloadProfileSeriesInput, downloadProfileSeriesSubmit, seasonsSubmit, globalMessage])

    function handleCancel() {
        clearWizardState()
        onCancel()
    }

    async function handleFinish() {
        // Build payload from current in-memory state to avoid race with async persistence
        const show = showSubmit
        const seasons = seasonsSubmit
        const localMediaProfile = localMediaProfileSubmit

        if (!show) {
            setWizardMessage('Please complete the "Choose show" step before finishing.', 'ERROR')
            return
        }
        if (!seasons) {
            setWizardMessage('Show seasons that should have been loaded in "Choose show" are not available.', 'ERROR')
            return
        }
        if (!localMediaProfile) {
            setWizardMessage('Please complete the Media Profile step before finishing.', 'ERROR')
            return
        }


        let downloadProfile;
        if (show.type === ShowTypeReg.Enum.podcast) {
            downloadProfile = downloadProfilePodcastSubmitRef.current ?? downloadProfilePodcastSubmit
        } else if (show.type === ShowTypeReg.Enum.series) {
            downloadProfile = downloadProfileSeriesSubmitRef.current ?? downloadProfileSeriesSubmit
        }
        if (!downloadProfile) {
            setWizardMessage('Please complete the Download Profile step before finishing.', 'ERROR')
            return
        }
        setWizardMessage('Validating...', 'INFO')

        const submitData = {
            show,
            seasons,
            localMediaProfile,
            downloadProfile,
        }
        console.log(JSON.stringify(submitData))

        try {
            const response = await fetch(`${(window as any).appConfig.API_URL}/shows/as-bundle`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify(submitData),
            })

            if (response.status !== 201) {
                let {error} = await getErrorMessageFromResponse(response)
                if (response.status === 409) {
                    error = "This show already exists"
                }
                setWizardMessage(error ?? `HTTP ${response.status}`, 'ERROR')
                return
            }

            clearWizardMessage()
        } catch (err) {
            setWizardMessage('Network error, please try again.', 'ERROR')
            return
        }

        await qc.invalidateQueries({queryKey: ['localMediaProfiles']})
        await qc.invalidateQueries({queryKey: ['downloadProfiles']})
        await qc.invalidateQueries({queryKey: ['shows']})
        await qc.invalidateQueries({queryKey: ['seasons']})
        clearWizardState()
        onCancel()
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
                    onSeasonsSubmit={setSeasonsSubmit}
                    onContinue={() => setStep(2)}
                    onCancel={handleCancel}
                />
            )}

            {step === 2 && (
                <LocalMediaProfileStep
                    value={localMediaProfileInput}
                    onChange={setLocalMediaProfileInput}
                    onSubmit={setLocalMediaProfileSubmit}
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
                        podcast: setPodcastDownloadProfileInput,
                        series: setSeriesDownloadProfileInput,
                    }}
                    onSubmit={{
                        podcast: (v) => {
                            setPodcastDownloadProfileSubmit(v)
                            downloadProfilePodcastSubmitRef.current = v
                        },
                        series: (v) => {
                            setSeriesDownloadProfileSubmit(v)
                            downloadProfileSeriesSubmitRef.current = v
                        },
                    }}
                    onBack={() => setStep(2)}
                    onFinish={handleFinish}
                    onCancel={handleCancel}
                    showSlug={showSubmit?.slug}
                    showType={showSubmit?.type}
                    seasons={seasonsSubmit as any}
                />
            )}
        </div>
    )
}
