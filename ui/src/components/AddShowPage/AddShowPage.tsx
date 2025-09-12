import { useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import UrlStep from './UrlStep'
import ProfileStep from './ProfileStep'
import ShowStep, {NewShowFormValue} from './ShowStep'
import type { MediaProfileFormValue } from '../MediaProfileForm'
import { defaultShowFormValue, type ShowFormValue } from '../ShowForm'

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

type ValidationResult = {
  domainOk: boolean
  pathOk: boolean
  slugOk: boolean
  errors: string[]
  normalized?: string
}

type MediaProfile = {
  id: number
  slug: string
  name: string
  outputTemplate: string
  preferredFormat: '4k' | '1080p' | '720p' | 'Audio Only'
  downloadSeriesImages: boolean
}

type NewProfileForm = MediaProfileFormValue

type WizardState = {
  step: 1 | 2 | 3
  rawUrl: string
  selectedProfileId: string | null
  newProfile: NewProfileForm
  newProfileState: NewProfileForm | null
  newShowForm: NewShowFormValue
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
    const payload: Versioned<WizardState> = { version: ver, data: state }
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

function ensureProtocol(input: string): string {
  let v = input.trim()
  if (!v) return v
  // If the string doesn't start with a URL scheme, prepend https://
  if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(v)) {
    v = 'https://' + v
  }
  return v
}

function validateShowUrl(input: string): ValidationResult {
  const withProto = ensureProtocol(input)

  try {
    const url = new URL(withProto)
    const host = url.hostname.toLowerCase()

    const domainOk = host === 'dailywire.com' || host === 'www.dailywire.com'
    const path = url.pathname

    const pathOk = path.startsWith('/show/')
    let slugOk = false
    if (pathOk) {
      const slug = path.slice('/show/'.length).split('/')[0]
      slugOk = !!slug
    }

    const errors: string[] = []
    if (!domainOk) errors.push('URL must be on dailywire.com')
    if (!pathOk) errors.push('URL must include /show/ in the path')
    if (!slugOk) errors.push('URL must include a show name after /show/ (e.g., the-ben-shapiro-show)')

    return { domainOk, pathOk, slugOk, errors, normalized: url.toString() }
  } catch {
    // If it's not parseable at all, surface all three rule errors
    return {
      domainOk: false,
      pathOk: false,
      slugOk: false,
      errors: [
        'URL must be on dailywire.com',
        'URL must include /show/ in the path',
        'URL must include a show name after /show/ (e.g., the-ben-shapiro-show)',
      ],
    }
  }
}

export default function AddShowPage({ onCancel }: Props) {
  const qc = useQueryClient()
  // Wizard step: 1 = URL, 2 = Media Profile, 3 = Show
  const [step, setStep] = useState<1 | 2 | 3>(() => loadWizardState()?.step ?? 1)

  // Step 1: URL
  const [rawUrl, setRawUrl] = useState(() => loadWizardState()?.rawUrl ?? '')
  const result = useMemo(() => validateShowUrl(rawUrl), [rawUrl])
  const urlValid = result.domainOk && result.pathOk && result.slugOk
  const showUrlErrors = rawUrl.trim().length > 0

  // Extract DailyWire show slug from the URL when valid
  const showSlug = useMemo(() => {
    if (!urlValid) return undefined
    try {
      const u = new URL(result.normalized ?? ensureProtocol(rawUrl))
      const path = u.pathname
      if (!path.startsWith('/show/')) return undefined
      const slug = path.slice('/show/'.length).split('/')[0]
      return slug || undefined
    } catch {
      return undefined
    }
  }, [urlValid, rawUrl, result.normalized])

  // Debounce to detect "done typing"
  const [debouncedSlug, setDebouncedSlug] = useState<string | undefined>(undefined)
  useEffect(() => {
    const h = setTimeout(() => setDebouncedSlug(showSlug), 500)
    return () => clearTimeout(h)
  }, [showSlug])


  // Step 2: Media Profile
  const [profiles, setProfiles] = useState<MediaProfile[] | null>(null)
  const [profilesError, setProfilesError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${(window as any).appConfig.API_URL}/media-profiles`, { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data = await r.json()
        setProfiles(data)
      })
      .catch((e: any) => {
        if (e.name !== 'AbortError') {
          console.error('Failed to load media profiles', e)
          setProfilesError('Failed to load media profiles')
          setProfiles([] as any)
        }
      })
    return () => controller.abort()
  }, [])
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(() => loadWizardState()?.selectedProfileId ?? null)
  const emptyProfile: NewProfileForm = {
    name: '',
    outputPathTemplate: '',
    preferredFormat: '1080p',
    downloadSeriesImages: true,
  }
  const [newProfile, setNewProfile] = useState<NewProfileForm>(() => loadWizardState()?.newProfile ?? emptyProfile)
  const [newProfileState, setNewProfileState] = useState<NewProfileForm | null>(() => loadWizardState()?.newProfileState ?? null)
  const [showForm, setShowForm] = useState<NewShowFormValue>(() => loadWizardState()?.newShowForm ?? { ...defaultShowFormValue })

  const creatingProfileValid =
    newProfile.name.trim().length > 0 && newProfile.outputPathTemplate.trim().length > 0
  const canContinueFromProfile = selectedProfileId !== null || creatingProfileValid

  // Persist wizard state on any change
  useEffect(() => {
    saveWizardState({ step, rawUrl, selectedProfileId, newProfile, newProfileState, newShowForm: showForm })
  }, [step, rawUrl, selectedProfileId, newProfile, newProfileState, showForm])

  function handleCancel() {
    clearWizardState()
    onCancel()
  }

  async function handleFinish() {
    // Ensure we have a media profile slug: use selected or create new
    let mediaProfileSlug = selectedProfileId
    if (!mediaProfileSlug) {
      const r = await fetch(`${(window as any).appConfig.API_URL}/media-profiles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newProfile),
      })
      if (!r.ok) {
        const msg = `Failed to create media profile (HTTP ${r.status})`
        console.error(msg)
        alert(msg)
        return
      }
      const created = await r.json()
      mediaProfileSlug = created.slug
      await qc.invalidateQueries({ queryKey: ['mediaProfiles'] })
    }

    const payload = {
      url: result.normalized ?? rawUrl,
      mediaProfileSlug,
      name: showForm.name,
      author: showForm.author,
      downloadMedia: showForm.downloadMedia,
      downloadDelayMinutes: showForm.downloadDelayMinutes,
      redownloadAfterMinutes: showForm.redownloadAfterMinutes,
      downloadDays: showForm.downloadDays,
      deleteOlder: showForm.deleteOlder,
      titleFilter: showForm.titleFilter,
    }

    const rs = await fetch(`${(window as any).appConfig.API_URL}/shows`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!rs.ok) {
      const msg = `Failed to create show (HTTP ${rs.status})`
      console.error(msg)
      alert(msg)
      return
    }
    await qc.invalidateQueries({ queryKey: ['shows'] })
    clearWizardState()
    onCancel()
  }

  return (
    <div>
      <div className="help" aria-live="polite" style={{ marginBottom: 12 }}>
        Step {step} of 3: {step === 1 ? 'URL' : step === 2 ? 'Media Profile' : 'Show'}
      </div>

      {step === 1 && (
        <UrlStep
          rawUrl={rawUrl}
          onChangeRawUrl={setRawUrl}
          urlValid={urlValid}
          showUrlErrors={showUrlErrors}
          errors={result.errors}
          onContinue={() => urlValid && setStep(2)}
          onCancel={handleCancel}
          slug={debouncedSlug}
        />
      )}

      {step === 2 && (
        <ProfileStep
          profiles={profiles}
          profilesError={profilesError}
          selectedProfileId={selectedProfileId}
          setSelectedProfileId={setSelectedProfileId}
          newProfile={newProfile}
          setNewProfile={setNewProfile}
          newProfileState={newProfileState}
          setNewProfileState={setNewProfileState}
          emptyProfile={{ ...emptyProfile }}
          canContinue={canContinueFromProfile}
          onBack={() => setStep(1)}
          onContinue={() => canContinueFromProfile && setStep(3)}
          onCancel={handleCancel}
        />
      )}

      {step === 3 && (
        <ShowStep
          normalizedUrl={result.normalized}
          rawUrl={rawUrl}
          newProfile={newProfile}
          showForm={showForm}
          setShowForm={setShowForm}
          onBack={() => setStep(2)}
          onFinish={handleFinish}
          onCancel={handleCancel}
        />
      )}
    </div>
  )
}
