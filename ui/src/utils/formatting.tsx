export function formatDate(value: Date | string | null | undefined) {
    if (!value) return '—'
    const d = value instanceof Date ? value : new Date(value)
    try {
        return new Intl.DateTimeFormat(undefined, {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        }).format(d)
    } catch {
        return d?.toString() ?? ''
    }
}

export function formatBytes(n: number | null | undefined) {
    if (!n && n !== 0) return ''
    if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GiB`
    if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MiB`
    return `${Math.round(n / 1024)} KiB`
}

export function formatDurationMinutes(minutes: number) {
    if (minutes === 0) return '0 minutes (the next monitor run)'
    const hours = Math.floor(minutes / 60)
    const remainingMinutes = minutes % 60
    const parts: string[] = []
    if (hours > 0) parts.push(`${hours} ${hours === 1 ? 'hour' : 'hours'}`)
    if (remainingMinutes > 0) {
        parts.push(`${remainingMinutes} ${remainingMinutes === 1 ? 'minute' : 'minutes'}`)
    }
    return parts.join(' ')
}