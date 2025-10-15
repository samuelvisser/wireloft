import React, {PropsWithChildren, useId, useState} from 'react'

export type PageSubtitleProps = {
  summary: React.ReactNode
  defaultExpanded?: boolean
  id?: string
  className?: string
  style?: React.CSSProperties
}

/**
 * PageSubtitle
 * - Lives directly under a page <h1> as a subtle subtitle.
 * - Provides an accessible toggle to reveal further explanation without using ReadMore.
 * - Designed to match the app's native look (light/dark aware via global CSS variables).
 */
export default function PageSubtitle({
  summary,
  children,
  defaultExpanded = false,
  id,
  className,
  style,
}: PropsWithChildren<PageSubtitleProps>) {
  const autoId = useId()
  const contentId = id ?? `page-subtitle-${autoId}`
  const [open, setOpen] = useState<boolean>(defaultExpanded)

  return (
    <div className={["page-subtitle", className].filter(Boolean).join(' ')} style={style}>
      <div className="page-subtitle-row">
        <p className="page-subtitle-text">{summary}</p>
        <button
          type="button"
          className="page-subtitle-toggle"
          aria-expanded={open}
          aria-controls={contentId}
          onClick={() => setOpen(v => !v)}
        >
          <span className="chev" aria-hidden>
            <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor" style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 160ms ease' }}>
              <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 10.94l3.71-3.71a.75.75 0 1 1 1.06 1.06l-4.24 4.24a.75.75 0 0 1-1.06 0L5.21 8.29a.75.75 0 0 1 .02-1.08z" />
            </svg>
          </span>
          <span>{open ? 'Hide details' : 'Learn more'}</span>
        </button>
      </div>
      {open && (
        <div id={contentId} className="page-subtitle-details">
          {children}
        </div>
      )}
    </div>
  )
}
