import { useCallback, useEffect, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import Sidebar from './components/Sidebar'
import Footer from './components/Sidebar/Footer'
import OnboardingFlow from './components/Onboarding/OnboardingFlow'
import BackgroundMigrationBanner from './components/BackgroundMigrationBanner/BackgroundMigrationBanner'
import LoginPage from './pages/LoginPage'

type OnboardingStatus = {
  completed: boolean
  adminPasswordConfigured: boolean
}

export default function App() {
  const navigate = useNavigate()

  const [authState, setAuthState] = useState<'checking' | 'ok' | 'no'>('checking')
  const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatus | null>(null)
  const [onboardingError, setOnboardingError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const base = (window as any).appConfig?.API_URL || '/api'
    fetch(`${base}/auth/status`, { credentials: 'include' })
      .then((r) => {
        if (cancelled) return
        setAuthState(r.ok ? 'ok' : 'no')
      })
      .catch(() => {
        if (cancelled) return
        setAuthState('no')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const loadOnboardingStatus = useCallback(async () => {
    setOnboardingError(null)
    try {
      const base = (window as any).appConfig?.API_URL || '/api'
      const response = await fetch(`${base}/onboarding/status`, { credentials: 'include' })
      if (response.status === 401) {
        setAuthState('no')
        return
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setOnboardingStatus(await response.json())
    } catch {
      setOnboardingError('WireLoft could not determine whether first-run setup is complete.')
    }
  }, [])

  useEffect(() => {
    if (authState !== 'ok') return
    void loadOnboardingStatus()
  }, [authState, loadOnboardingStatus])

  if (authState === 'checking') {
    return null
  }

  if (authState === 'no') {
    return <LoginPage />
  }

  if (!onboardingStatus) {
    if (!onboardingError) return null
    return (
      <div className="onboarding-bootstrap">
        <div>
          <p role="alert">{onboardingError}</p>
          <button className="btn btn-primary" type="button" onClick={() => void loadOnboardingStatus()}>
            Try again
          </button>
        </div>
      </div>
    )
  }

  if (!onboardingStatus.completed) {
    return (
      <OnboardingFlow
        adminPasswordConfigured={onboardingStatus.adminPasswordConfigured}
        onComplete={() => {
          setOnboardingStatus((current) => current ? { ...current, completed: true } : current)
          navigate('/', { replace: true })
          toast.success(
            'WireLoft is setup. Look around a little and explore your very own media manager for all things Daily Wire. Enjoy!',
            { duration: 8000 },
          )
        }}
      />
    )
  }

  return (
    <div className="app">
      <Sidebar />
      <main className="content" role="main">
        {/* Deliberately mounted only after onboarding so first-run setup never shows this banner. */}
        <BackgroundMigrationBanner />
        <Outlet />
      </main>
      <Footer wrapperClass="page-footer" />
    </div>
  )
}
