export async function loadAppConfig() {
  try {
    const res = await fetch('/config.json', { cache: 'no-store' })
    if (!res.ok) {
      throw new Error(`Failed to load config.json: ${res.status} ${res.statusText}`)
    }
    const cfg = await res.json()
    window.appConfig = { ...(window.appConfig || {}), ...cfg }
  } catch (err) {
    console.error('[appConfig] Error loading config.json', err)
    window.appConfig = window.appConfig || {}
  }
}
