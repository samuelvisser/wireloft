import type {IconProp} from '@fortawesome/fontawesome-svg-core'

export type ProgressPresentation = {
    mode: 'determinate' | 'indeterminate' | 'waiting' | 'terminal'
    active: boolean
    percent: number | null
    label: string
    compactLabel?: string
    detail: string
    icon: IconProp
    secondary?: string
    estimated?: boolean
    canCancel: boolean
    canRetry: boolean
    outcome?: 'success' | 'error' | 'canceled'
}

export type DownloadPresentation = ProgressPresentation & {status: string}
