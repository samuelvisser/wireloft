import {useEffect, useRef, useState} from 'react'
import {getCurrentAppVersion, getErrorMessageFromResponse} from '../../utils/helpers'
import ChooseShowStep from './ChooseShowStep'
import ShowActionStep, {ShowAction} from './ShowActionStep'
import LocalMediaProfileStep from './LocalMediaProfileStep'
import DownloadProfileStep from './DownloadProfileStep'
import StreamProfileStep from './StreamProfileStep'

import type {Versioned} from '../../types/data'
import {ShowCreatePayloadOut, ShowCreatePayloadIn, ShowCreatePayloadSchema} from "../../types/schemas/show";
import {getZodDefaults} from "../../utils/defaultZod";
import {
    PodcastDownloadProfileBundleSchema,
    SeriesDownloadProfileBundleSchema, DownloadProfileUnifiedCreateIn, DownloadProfileUnifiedCreateOut,
    LocalMediaProfileCreateUnionSchema,
    LocalMediaProfileUpsertIn,
    LocalMediaProfileUpsertOut,
    RssStreamProfileBundleIn,
    RssStreamProfileBundleOut,
} from "../../types/schemas/show_as_bundle";
import {ShowTypeReg} from "../../types/show";
import {useQueryClient} from "@tanstack/react-query";
import {SeasonDetachedOut} from "../../types/schemas/season";

export type Props = {
    onCancel: () => void
}

const STORAGE_KEY = 'addShowWizardV8'

type WizardType = 'ERROR' | 'INFO'
type WizardMessage = { text: string; type: WizardType }
type WizardStep = 1 | 2 | 3 | 4 | 5

type WizardState = {
    step: WizardStep
    action?: ShowAction
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
    streamProfile: {
        input: Partial<RssStreamProfileBundleIn>,
        submit: RssStreamProfileBundleOut | undefined,
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
        if (parsed && typeof parsed === 'object' && 'version' in parsed && 'data' in parsed) {
            if (typeof current === 'string') {
                if (parsed.version === current) return parsed.data as WizardState
                localStorage.removeItem(STORAGE_KEY)
                return null
            }
            return null
        }
        if (typeof current === 'string') localStorage.removeItem(STORAGE_KEY)
        return null
    } catch {
        return null
    }
}

function saveWizardState(state: WizardState) {
    try {
        const ver = getCurrentAppVersion()
        if (!ver) return
        const payload: Versioned<WizardState> = {version: ver, data: state}
        localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
        // ignore write errors
    }
}

function clearWizardState() {
    try {
        localStorage.removeItem(STORAGE_KEY)
    } catch {
        // ignore
    }
}

const defaultStreamProfile = (action?: ShowAction): Partial<RssStreamProfileBundleIn> => ({
    enableProfile: true,
    useDownloads: action === 'download-stream',
    useDwStream: action !== 'download-stream',
    preferredFormat: 'format_1080p',
    requireExactMatch: false,
})

export default function AddShowPage({onCancel}: Props) {
    const persisted = loadWizardState()
    const [globalMessage, setGlobalMessage] = useState<WizardMessage | null>(() => persisted?.globalMessage ?? null)
    const [isFinishing, setIsFinishing] = useState(false)
    const setWizardMessage = (message: string, type: WizardType) => setGlobalMessage({text: message, type})
    const clearWizardMessage = () => setGlobalMessage(null)
    const qc = useQueryClient()

    const [step, setStep] = useState<WizardStep>(() => persisted?.step ?? 1)
    const [showAction, setShowAction] = useState<ShowAction | undefined>(() => persisted?.action)

    const [showInput, setShowInput] = useState<Partial<ShowCreatePayloadIn>>(
        () => persisted?.show.input ?? getZodDefaults(ShowCreatePayloadSchema))
    const [showSubmit, setShowSubmit] = useState<ShowCreatePayloadOut | undefined>(() => persisted?.show.submit)

    const [localMediaProfileInput, setLocalMediaProfileInput] = useState<Partial<LocalMediaProfileUpsertIn>>(
        () => persisted?.localMediaProfile.input ?? getZodDefaults(LocalMediaProfileCreateUnionSchema))
    const [localMediaProfileSubmit, setLocalMediaProfileSubmit] = useState<LocalMediaProfileUpsertOut | undefined>(() => persisted?.localMediaProfile.submit)

    const [downloadProfilePodcastInput, setPodcastDownloadProfileInput] = useState<Partial<DownloadProfileUnifiedCreateIn>>(
        () => persisted?.downloadProfile.podcast.input ?? getZodDefaults(PodcastDownloadProfileBundleSchema))
    const [downloadProfilePodcastSubmit, setPodcastDownloadProfileSubmit] = useState<DownloadProfileUnifiedCreateOut | undefined>(() => persisted?.downloadProfile.podcast.submit)

    const [downloadProfileSeriesInput, setSeriesDownloadProfileInput] = useState<Partial<DownloadProfileUnifiedCreateIn>>(
        () => persisted?.downloadProfile.series.input ?? getZodDefaults(SeriesDownloadProfileBundleSchema))
    const [downloadProfileSeriesSubmit, setSeriesDownloadProfileSubmit] = useState<DownloadProfileUnifiedCreateOut | undefined>(() => persisted?.downloadProfile.series.submit)

    const [streamProfileInput, setStreamProfileInput] = useState<Partial<RssStreamProfileBundleIn>>(
        () => persisted?.streamProfile?.input ?? defaultStreamProfile(persisted?.action))
    const [streamProfileSubmit, setStreamProfileSubmit] = useState<RssStreamProfileBundleOut | undefined>(
        () => persisted?.streamProfile?.submit)

    const [seasonsSubmit, setSeasonsSubmit] = useState<SeasonDetachedOut[] | undefined>(() => persisted?.seasons ?? [])

    const downloadProfilePodcastSubmitRef = useRef(downloadProfilePodcastSubmit)
    const downloadProfileSeriesSubmitRef = useRef(downloadProfileSeriesSubmit)
    const streamProfileSubmitRef = useRef(streamProfileSubmit)

    useEffect(() => {
        saveWizardState({
            step,
            action: showAction,
            show: {input: showInput, submit: showSubmit},
            localMediaProfile: {input: localMediaProfileInput, submit: localMediaProfileSubmit},
            downloadProfile: {
                podcast: {input: downloadProfilePodcastInput, submit: downloadProfilePodcastSubmit},
                series: {input: downloadProfileSeriesInput, submit: downloadProfileSeriesSubmit},
            },
            streamProfile: {input: streamProfileInput, submit: streamProfileSubmit},
            seasons: seasonsSubmit,
            globalMessage,
        })
    }, [step, showAction, showInput, showSubmit, localMediaProfileInput, localMediaProfileSubmit,
        downloadProfilePodcastInput, downloadProfilePodcastSubmit, downloadProfileSeriesInput,
        downloadProfileSeriesSubmit, streamProfileInput, streamProfileSubmit, seasonsSubmit, globalMessage])

    function handleCancel() {
        clearWizardState()
        onCancel()
    }

    async function handleFinish(actionOverride?: ShowAction) {
        const action = actionOverride ?? showAction
        const show = showSubmit
        const seasons = seasonsSubmit

        if (!action || !show || !seasons) {
            setWizardMessage('The show setup is incomplete. Please go back and complete the previous steps.', 'ERROR')
            return
        }

        let localMediaProfile: LocalMediaProfileUpsertOut | undefined
        let downloadProfile: DownloadProfileUnifiedCreateOut | undefined
        let streamProfile: RssStreamProfileBundleOut | undefined

        if (action === 'download-stream') {
            localMediaProfile = localMediaProfileSubmit
            if (!localMediaProfile) {
                setWizardMessage('Please complete the Media Profile step before finishing.', 'ERROR')
                return
            }
            downloadProfile = show.type === ShowTypeReg.Enum.podcast
                ? (downloadProfilePodcastSubmitRef.current ?? downloadProfilePodcastSubmit)
                : (downloadProfileSeriesSubmitRef.current ?? downloadProfileSeriesSubmit)
            if (!downloadProfile) {
                setWizardMessage('Please complete the Download Profile step before finishing.', 'ERROR')
                return
            }
        }

        if (action === 'stream' || action === 'download-stream') {
            streamProfile = streamProfileSubmitRef.current ?? streamProfileSubmit
            if (!streamProfile) {
                setWizardMessage('Please complete the Stream Profile step before finishing.', 'ERROR')
                return
            }
        }

        setIsFinishing(true)
        setWizardMessage('Saving show...', 'INFO')

        const submitData = {
            show,
            seasons,
            ...(localMediaProfile ? {localMediaProfile} : {}),
            ...(downloadProfile ? {downloadProfile} : {}),
            ...(streamProfile ? {streamProfile} : {}),
        }

        try {
            const response = await fetch(`${(window as any).appConfig.API_URL}/shows/as-bundle`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify(submitData),
            })

            if (response.status !== 201) {
                let {error} = await getErrorMessageFromResponse(response)
                if (response.status === 409) error = 'This show already exists'
                setWizardMessage(error ?? `HTTP ${response.status}`, 'ERROR')
                return
            }
            clearWizardMessage()
        } catch {
            setWizardMessage('Network error, please try again.', 'ERROR')
            return
        } finally {
            setIsFinishing(false)
        }

        await Promise.all([
            qc.invalidateQueries({queryKey: ['localMediaProfiles']}),
            qc.invalidateQueries({queryKey: ['downloadProfiles']}),
            qc.invalidateQueries({queryKey: ['rssStreamProfiles']}),
            qc.invalidateQueries({queryKey: ['streamProfilesView']}),
            qc.invalidateQueries({queryKey: ['shows']}),
            qc.invalidateQueries({queryKey: ['seasons']}),
        ])
        clearWizardState()
        onCancel()
    }

    async function handleActionContinue() {
        if (!showAction) return
        if (showAction === 'index') {
            await handleFinish('index')
            return
        }
        setStreamProfileInput((current) => ({...defaultStreamProfile(showAction), ...current,
            useDownloads: showAction === 'download-stream',
            useDwStream: showAction !== 'download-stream',
        }))
        setStep(3)
    }

    const totalSteps = showAction === 'download-stream' ? 5 : showAction === 'stream' ? 3 : 2
    const stepTitle = step === 1 ? 'Choose show'
        : step === 2 ? 'Choose what WireLoft should do'
        : showAction === 'stream' ? 'Stream Profile'
        : step === 3 ? 'Media Profile'
        : step === 4
            ? (showSubmit?.type === ShowTypeReg.Enum.podcast ? 'Download Profile for Podcasts'
                : showSubmit?.type === ShowTypeReg.Enum.series ? 'Download Profile for Series' : 'Download Profile')
            : 'Stream Profile'

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
                Step {step} of {totalSteps}: {stepTitle}
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
                <ShowActionStep
                    value={showAction}
                    onChange={setShowAction}
                    onBack={() => setStep(1)}
                    onContinue={handleActionContinue}
                    onCancel={handleCancel}
                    isSubmitting={isFinishing}
                />
            )}

            {step === 3 && showAction === 'stream' && (
                <StreamProfileStep
                    value={streamProfileInput}
                    onChange={setStreamProfileInput}
                    onSubmit={(value) => {
                        setStreamProfileSubmit(value)
                        streamProfileSubmitRef.current = value
                    }}
                    onBack={() => setStep(2)}
                    onFinish={() => handleFinish('stream')}
                    onCancel={handleCancel}
                    showSlug={showSubmit?.slug}
                />
            )}

            {step === 3 && showAction === 'download-stream' && (
                <LocalMediaProfileStep
                    value={localMediaProfileInput}
                    onChange={setLocalMediaProfileInput}
                    onSubmit={setLocalMediaProfileSubmit}
                    onBack={() => setStep(2)}
                    onContinue={() => setStep(4)}
                    onCancel={handleCancel}
                    showSlug={showSubmit?.slug}
                />
            )}

            {step === 4 && showAction === 'download-stream' && (
                <DownloadProfileStep
                    value={{podcast: downloadProfilePodcastInput, series: downloadProfileSeriesInput}}
                    onChange={{podcast: setPodcastDownloadProfileInput, series: setSeriesDownloadProfileInput}}
                    onSubmit={{
                        podcast: (value) => {
                            setPodcastDownloadProfileSubmit(value)
                            downloadProfilePodcastSubmitRef.current = value
                        },
                        series: (value) => {
                            setSeriesDownloadProfileSubmit(value)
                            downloadProfileSeriesSubmitRef.current = value
                        },
                    }}
                    onBack={() => setStep(3)}
                    onFinish={() => setStep(5)}
                    onCancel={handleCancel}
                    showSlug={showSubmit?.slug}
                    showType={showSubmit?.type}
                    seasons={seasonsSubmit as any}
                />
            )}

            {step === 5 && showAction === 'download-stream' && (
                <StreamProfileStep
                    value={streamProfileInput}
                    onChange={setStreamProfileInput}
                    onSubmit={(value) => {
                        setStreamProfileSubmit(value)
                        streamProfileSubmitRef.current = value
                    }}
                    onBack={() => setStep(4)}
                    onFinish={() => handleFinish('download-stream')}
                    onCancel={handleCancel}
                    showSlug={showSubmit?.slug}
                />
            )}
        </div>
    )
}
