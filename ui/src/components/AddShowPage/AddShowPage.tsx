import {useEffect, useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import ChooseShowStep, {type ShowFormValue} from './ChooseShowStep'
import MediaProfileStep from './MediaProfileStep'
import DownloadProfileStep, {type DownloadProfileFormValue} from './DownloadProfileStep'
import type {AddShowMediaProfileUpsert} from '../../types/addShow'

export type Props = {
    onCancel: () => void
}

// Wizard state persistence
const STORAGE_KEY = 'addShowWizardV1'

type Versioned<T> = {
    version: string
    data: T
}

function getCurrentAppVersion(): string | undefined {
    try {
        return (window as any).appConfig?.APP_VERSION
    } catch {
        return undefined
    }
}

type WizardState = {
    step: 1 | 2 | 3
    show: ShowFormValue
    mediaProfile: AddShowMediaProfileUpsert
    downloadProfile: DownloadProfileFormValue
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
            // If version is unknown, don't persist to avoid stale format
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

    // Step 1: Show (managed inside ChooseShowStep)
    const [show, setShow] = useState<ShowFormValue>(() => loadWizardState()?.show ?? ({
        rawUrl: '',
        showType: null,
        episodeIdentifier: null
    }))
    const [slug, setSlug] = useState<string | undefined>(undefined)


    // Step 2: Media Profile (managed inside MediaProfileStep)
    const defaultMediaProfile: AddShowMediaProfileUpsert = {
        op: 'create_new',
        name: '',
        outputTemplate: '',
        preferredFormat: '1080p',
        downloadSeriesImages: true,
    }
    const [mediaProfile, setMediaProfile] = useState<AddShowMediaProfileUpsert>(
        () => (loadWizardState() as any)?.mediaProfile ?? {...defaultMediaProfile}
    )

    const defaultDownloadProfile: DownloadProfileFormValue = {
        enableProfile: true,
        downloadWithCountdown: false,
        redownloadFinal: false,
        downloadDaysInPast: 0,
        deleteOlderEpisodes: true,
    }
    const [downloadProfile, setDownloadProfile] = useState<DownloadProfileFormValue>(
        () => loadWizardState()?.downloadProfile ?? {...defaultDownloadProfile}
    )


    // Persist wizard state on any change
    useEffect(() => {
        saveWizardState({
            step,
            show,
            mediaProfile,
            downloadProfile,
        })
    }, [step, show, mediaProfile, downloadProfile])

    function handleCancel() {
        clearWizardState()
        onCancel()
    }

    async function handleFinish() {
        // Ensure we have a media profile slug: use selected or create new

        // TODO save show to /api/shows/show-with-profiles

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
                    value={show}
                    onChange={setShow}
                    onContinue={() => setStep(2)}
                    onCancel={handleCancel}
                    onSlugChange={setSlug}
                />
            )}

            {step === 2 && (
                <MediaProfileStep
                    value={mediaProfile}
                    onChange={setMediaProfile}
                    onBack={() => setStep(1)}
                    onContinue={() => setStep(3)}
                    onCancel={handleCancel}
                    slug={slug}
                />
            )}

            {step === 3 && (
                <DownloadProfileStep
                    value={downloadProfile}
                    onChange={setDownloadProfile}
                    onBack={() => setStep(2)}
                    onFinish={handleFinish}
                    onCancel={handleCancel}
                    slug={slug}
                />
            )}
        </div>
    )
}
