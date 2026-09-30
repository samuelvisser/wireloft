import type {ProgressPresentation} from '../../types/progress'
import './ProgressVisual.css'

export default function ProgressFill({presentation, className = ''}: {presentation: Pick<ProgressPresentation, 'mode' | 'percent'>; className?: string}) {
    const percent = presentation.percent == null ? undefined : Math.max(0, Math.min(100, presentation.percent))
    return <span aria-hidden="true" className={`wl-progress-fill is-${presentation.mode} ${className}`}
                 style={{width: presentation.mode === 'indeterminate' ? undefined : `${percent ?? 100}%`}}/>
}
