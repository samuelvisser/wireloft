import type {ProgressPresentation} from '../../types/progress'
import ProgressFill from './ProgressFill'

type ProgressBarProps = {
    value?: number | null
    mode?: ProgressPresentation['mode']
    ariaLabel?: string
    detail?: string
}

export default function ProgressBar({value = null, mode = value == null ? 'indeterminate' : 'determinate', ariaLabel, detail}: ProgressBarProps) {
    const percent = value == null ? null : Math.max(0, Math.min(100, Math.round(value)))
    return <span className="progress wl-progress-track" role="progressbar" aria-label={ariaLabel} aria-valuetext={detail}
                 aria-valuemin={0} aria-valuemax={100} aria-valuenow={mode === 'determinate' ? percent ?? undefined : undefined}>
        <ProgressFill presentation={{mode, percent}}/>
    </span>
}
