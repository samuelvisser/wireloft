import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { buildServerAwareSubmit } from '../utils/buildServerAwareSubmit'

const LoginSchema = z.object({
  password: z.string().min(7, 'Password must be at least 7 characters'),
})
type LoginValues = z.infer<typeof LoginSchema>

export default function LoginPage() {
  const form = useForm<LoginValues>({
    resolver: zodResolver(LoginSchema),
    defaultValues: { password: '' },
    shouldFocusError: true,
  })

  const handleSubmit = buildServerAwareSubmit<LoginValues>(
    form,
    async (data) => {
      const base = (window as any).appConfig?.API_URL || '/api'
      return await fetch(`${base}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(data),
      })
    },
    {
      // login returns 204 No Content
      successStatuses: [204],
      onSuccess: async () => {
        // Reload to let the app re-check auth
        window.location.reload()
      },
      fallbackField: 'password',
      rootServerValidationMessage: 'Login failed. Please check the password and try again.',
    },
  )

  const {
    register,
    formState: { errors },
  } = form

  return (
    <div className="login-page" style={{ display: 'grid', placeItems: 'center', minHeight: '100vh', background: 'linear-gradient(135deg, #0b1020, #1b1f3b)' }}>
      <div style={{ width: 'min(440px, 92vw)', background: 'rgba(0,0,0,0.4)', borderRadius: 16, padding: 28, boxShadow: '0 20px 60px rgba(0,0,0,0.5)', border: '1px solid rgba(255,255,255,0.08)' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, marginBottom: 18 }}>
          <img src="/logo-square-full.png" alt="WireLoft" style={{ width: 200, objectFit: 'contain', filter: 'drop-shadow(0 6px 16px rgba(0,0,0,0.5))' }} />
          <h1 style={{ color: 'white', fontSize: 24, margin: 0, fontWeight: 600 }}>Welcome</h1>
          <p style={{ color: 'rgba(255,255,255,0.7)', margin: 0, fontSize: 14 }}>Enter the admin password to continue</p>
        </div>

        {/* Root error banner */}
        {errors.root && (
          <div role="alert" style={{ background: 'rgba(255, 77, 77, 0.12)', color: '#ffb3b3', border: '1px solid rgba(255,77,77,0.3)', borderRadius: 10, padding: '10px 12px', marginBottom: 12 }}>
            {errors.root.message?.toString()}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ display: 'grid', gap: 10 }}>
            <label htmlFor="password" style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13 }}>Password</label>
            <input
              id="password"
              type="password"
              autoFocus
              {...register('password')}
              placeholder="Enter password"
              style={{
                WebkitAppearance: 'none',
                background: 'rgba(255,255,255,0.07)',
                border: `1px solid ${errors.password ? 'rgba(255,77,77,0.5)' : 'rgba(255,255,255,0.15)'}`,
                color: 'white',
                padding: '12px 14px',
                borderRadius: 10,
                outline: 'none',
                fontSize: 14,
                boxShadow: errors.password ? '0 0 0 3px rgba(255,77,77,0.15)' : 'none',
              }}
            />
            {errors.password && (
              <div role="alert" style={{ color: '#ffb3b3', fontSize: 12 }}>{errors.password.message?.toString()}</div>
            )}

            <button type="submit" style={{ marginTop: 12, background: 'linear-gradient(135deg, #4a6bff, #5f9dff)', color: 'white', fontWeight: 600, border: 'none', borderRadius: 10, padding: '12px 14px', fontSize: 14, cursor: 'pointer', boxShadow: '0 10px 20px rgba(79,131,255,0.25)' }}>
              Unlock
            </button>
          </div>
        </form>

        <div style={{ marginTop: 18, textAlign: 'center', color: 'rgba(255,255,255,0.55)', fontSize: 12 }}>
          Protected by local password set by the admin. Only authorized users are allowed to access WireLoft.
        </div>
      </div>
    </div>
  )
}
