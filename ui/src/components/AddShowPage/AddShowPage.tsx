import {useEffect, useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import {getCurrentAppVersion} from '../../utils/helpers'
import ChooseShowStep from './ChooseShowStep'
import MediaProfileStep from './MediaProfileStep'
import DownloadProfileStep from './DownloadProfileStep'

import type {Versioned} from '../../types/data'
import {ShowCreatePayloadOut, ShowCreatePayloadIn, ShowCreatePayloadSchema} from "../../types/schemas/show";
import {getZodDefaults} from "../../utils/defaultZod";
import {MediaProfileUpsertIn, MediaProfileUpsertOut} from "../../types/schemas/show_with_profiles";

export type Props = {
    onCancel: () => void
}

// Wizard state persistence
const STORAGE_KEY = 'addShowWizardV3'

type WizardState = {
    step: 1 | 2 | 3
    show: {
        input: ShowCreatePayloadIn,
        submit: ShowCreatePayloadOut | undefined,
    },
    mediaProfile: {
        input: MediaProfileUpsertIn,
        submit: MediaProfileUpsertOut | undefined,
    }
    // mediaProfile: MediaProfileCreate
    // downloadProfile: DownloadProfileSeriesCreate | DownloadProfilePodcastCreate
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
    const qc = useQueryClient()
    // Wizard step: 1 = URL, 2 = Media Profile, 3 = Show
    const [step, setStep] = useState<1 | 2 | 3>(() => loadWizardState()?.step ?? 1)


    const [showInput, setShowInput] = useState<ShowCreatePayloadIn>(
        () => loadWizardState()?.show.input ?? getZodDefaults(ShowCreatePayloadSchema))
    const [showSubmit, setShowSubmit] = useState<ShowCreatePayloadOut>()

    const [mediaProfileInput, setMediaProfileInput] = useState<MediaProfileUpsertIn>(
        () => loadWizardState()?.mediaProfile.input ?? {
            op: "create_new",
            name: "",
            outputTemplate: "/downloads/",
            preferredFormat: "format_1080p",
            downloadSeriesImages: false,
        })
    const [mediaProfileSubmit, setMediaProfileSubmit] = useState<MediaProfileUpsertOut>()



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
            }
            // downloadProfile,
        })
    }, [step, showInput, showSubmit, mediaProfileInput, mediaProfileSubmit,
        // downloadProfile
    ])

    function handleCancel() {
        clearWizardState()
        onCancel()
    }

    async function handleFinish() {
        // Ensure we have a media profile slug: use selected or create new
        await qc.invalidateQueries({queryKey: ['mediaProfiles']})
        await qc.invalidateQueries({queryKey: ['shows']})
        clearWizardState()
        onCancel()
    }

    return (
        <div>
            <div className="help" aria-live="polite" style={{marginBottom: 12}}>
                Step {step} of 3: {step === 1 ? 'Choose show' : step === 2 ? 'Media Profile' : 'Download Profile'}
            </div>

            {step === 1 && (
                <ChooseShowStep
                    value={showInput}
                    onChange={setShowInput}
                    onContinue={(data: ShowCreatePayloadOut) => {
                        setShowSubmit(data)
                        setStep(2)
                    }}
                    onCancel={handleCancel}
                />
            )}

            {step === 2 && (
                <MediaProfileStep
                    value={mediaProfileInput}
                    onChange={setMediaProfileInput}
                    onBack={() => setStep(1)}
                    onContinue={(data: MediaProfileUpsertOut) => {
                        setMediaProfileSubmit(data)
                        setStep(3)
                    }}
                    onCancel={handleCancel}
                    showSlug={showSubmit?.slug}
                />
            )}

            {step === 3 && (
                <DownloadProfileStep
                    onBack={() => setStep(2)}
                    onFinish={handleFinish}
                    onCancel={handleCancel}
                    showSlug={showSubmit?.slug}
                    showType={showSubmit?.type}
                />
            )}
        </div>
    )
}
