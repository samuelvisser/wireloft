import { useMemo } from 'react'

export type ShowFormValue = {
  name: string
  author: string
  downloadMedia: boolean
  downloadDays: string // keep string to allow empty input
  deleteOlder: boolean
  titleFilter: string
}

function formatISODate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

type Props = {
  value: ShowFormValue
  onChange: (value: ShowFormValue) => void
}

export default function ShowForm({ value, onChange }: Props) {
  const oldestDateHelp = useMemo(() => {
    const n = parseInt(value.downloadDays, 10)
    if (!isFinite(n) || isNaN(n) || n < 0) return ''
    const now = new Date()
    const d = new Date(now)
    d.setDate(now.getDate() - n)
    return `Oldest date in range: ${formatISODate(d)}`
  }, [value.downloadDays])

  return (
    <>
      <div className="form-row">
        <label htmlFor="show-name">Show name</label>
        <input
          id="show-name"
          className="input"
          type="text"
          placeholder="The Ben Shapiro Show"
          value={value.name}
          onChange={(e) => onChange({ ...value, name: e.target.value })}
        />
      </div>

      <div className="form-row">
        <label htmlFor="show-author">Author</label>
        <input
          id="show-author"
          className="input"
          type="text"
          placeholder="Ben Shapiro"
          value={value.author}
          onChange={(e) => onChange({ ...value, author: e.target.value })}
        />
      </div>

      <div className="form-row" style={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <label htmlFor="download-media">Download media</label>
        <label className="switch-control">
          <input
            id="download-media"
            className="switch-input"
            type="checkbox"
            checked={value.downloadMedia}
            onChange={(e) => onChange({ ...value, downloadMedia: e.target.checked })}
          />
          <span className="switch" aria-hidden="true"></span>
        </label>
      </div>

      <div className="form-row">
        <label htmlFor="download-days">Download days in the past</label>
        <input
          id="download-days"
          className="input"
          type="number"
          inputMode="numeric"
          min={0}
          step={1}
          placeholder="e.g. 180"
          value={value.downloadDays}
          onChange={(e) => onChange({ ...value, downloadDays: e.target.value })}
        />
        {value.downloadDays.trim() !== '' && (
          <div className="help" aria-live="polite">{oldestDateHelp}</div>
        )}
      </div>

      <div className="form-row" style={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <label htmlFor="delete-older">Delete older episodes</label>
        <label className="switch-control">
          <input
            id="delete-older"
            className="switch-input"
            type="checkbox"
            checked={value.deleteOlder}
            onChange={(e) => onChange({ ...value, deleteOlder: e.target.checked })}
          />
          <span className="switch" aria-hidden="true"></span>
        </label>
      </div>

      <div className="form-row">
        <label htmlFor="title-filter">Title filter</label>
        <input
          id="title-filter"
          className="input"
          type="text"
          placeholder="e.g. [Member Exclusive]"
          value={value.titleFilter}
          onChange={(e) => onChange({ ...value, titleFilter: e.target.value })}
        />
        <div className="help">Only episodes matching this title pattern will be processed.</div>
      </div>
    </>
  )
}
