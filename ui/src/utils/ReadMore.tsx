import { PropsWithChildren, useId, useState } from 'react'

export type ReadMoreProps = {
  summary: React.ReactNode
  initiallyExpanded?: boolean
  id?: string
  className?: string
  style?: React.CSSProperties
  // If true, stop propagation on toggle clicks (useful inside labels/controls)
  stopPropagation?: boolean
  // Optional callback
  onToggle?: (expanded: boolean) => void
}

/**
 * Inline "Read more / Show less" helper for help texts.
 * - Keeps the toggle button visually subtle and inline with text
 * - Accessible via aria-expanded and aria-controls
 * - Minimal styles to blend with current UI help text
 */
export default function ReadMore({
  summary,
  children,
  initiallyExpanded = false,
  id,
  className,
  style,
  stopPropagation = true,
  onToggle,
}: PropsWithChildren<ReadMoreProps>) {
  const autoId = useId()
  const detailsId = id ?? `readmore-${autoId}`
  const [expanded, setExpanded] = useState( initiallyExpanded )

  const handleClick: React.MouseEventHandler<HTMLButtonElement> = (e) => {
    e.preventDefault()
    if (stopPropagation) e.stopPropagation()
    setExpanded(v => {
      const next = !v
      onToggle?.(next)
      return next
    })
  }

  return (
    <span className={className} style={style}>
      <span>{summary}</span>{' '}
      <button
        type="button"
        onClick={handleClick}
        aria-expanded={expanded}
        aria-controls={detailsId}
        style={{ background: 'none', border: 'none', padding: 0, color: 'inherit', textDecoration: 'underline', cursor: 'pointer' }}
      >
        {expanded ? 'Show less' : 'Read more'}
      </button>
      {expanded && (
        <div id={detailsId} style={{ marginTop: 4 }}>
          {children}
        </div>
      )}
    </span>
  )
}

export { ReadMore }
