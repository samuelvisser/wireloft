type ProgressBarProps = {
    /** 0-100 */
    value: number
    ariaLabel?: string
}

export default function ProgressBar({value, ariaLabel}: ProgressBarProps) {
    const pct = Math.max(0, Math.min(100, Math.round(value)))
    return (
        <div
            className="progress"
            role="progressbar"
            aria-label={ariaLabel}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            style={{height: 6, background: 'var(--divider, #eee)', borderRadius: 999, overflow: 'hidden'}}
        >
            <div
                className="progress-fill"
                style={{
                    width: `${pct}%`,
                    height: '100%',
                    background: '#0d6efd',
                    transition: 'width 0.3s ease',
                }}
            />
        </div>
    )
}
