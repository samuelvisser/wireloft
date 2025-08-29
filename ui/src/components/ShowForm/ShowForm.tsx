import { useMemo } from 'react'
import ReadMore from '../../utils/ReadMore'
import TimeInterval from '../../utils/TimeInterval'

export type ShowFormValue = {
  name: string
  author: string
  downloadMedia: boolean
  downloadDelayMinutes: string
  redownloadAfterMinutes: string
  downloadDays: string // keep string to allow empty input
  deleteOlder: boolean
  titleFilter: string
}

export const defaultShowFormValue: ShowFormValue = {
  name: '',
  author: '',
  downloadMedia: true,
  downloadDelayMinutes: '90',
  redownloadAfterMinutes: '180',
  downloadDays: '180',
  deleteOlder: true,
  titleFilter: '',
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

  const redownloadMinutesHelp = useMemo(() => {
    const n = parseInt(value.redownloadAfterMinutes, 10)
    if (!isFinite(n) || isNaN(n) || n < 0) return ''
     const base = new Date()
    base.setHours(18, 0, 0, 0)
    const target = new Date(base.getTime() + n * 60_000)
    const hh = String(target.getHours()).padStart(2, '0')
    const mm = String(target.getMinutes()).padStart(2, '0')
    const dayNote = target.getDate() !== base.getDate() ? ' (next day)' : ''

    return `If the show was published at 18:00, we will re-download it at ${hh}:${mm}${dayNote}`
  }, [value.redownloadAfterMinutes])


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
        <label htmlFor="download-delay-h">Initial download delay</label>
        <TimeInterval
            idPrefix="download-delay"
            value={value.downloadDelayMinutes}
            onChange={(m) => onChange({ ...value, downloadDelayMinutes: m })}
            hoursLabel="hours"
            minutesLabel="minutes"
        />

        <div className="help" aria-live="polite">
        <ReadMore summary={"Download as soon as it's available (may include the pre-show countdown)."}>
          After about 10 minutes of a show going live, it's usually available on The Daily Wire website. However, that recording includes everything from the live stream start, which often means the pre-show countdown.
          If you enable this option, we'll download as soon as it's available (and you might get the countdown). If you leave it off, we'll wait roughly one hour so the countdown is usually removed.
          Unfortunately, we can't reliably detect when the countdown is gone, so even disabling this doesn't guarantee you'll never download the countdown.
        </ReadMore>
        </div>

      </div>

      <div className="form-row">
        <label htmlFor="redownload-after-h">Redownload delay</label>
        <TimeInterval
          idPrefix="redownload-after"
          value={value.redownloadAfterMinutes}
          onChange={(m) => onChange({ ...value, redownloadAfterMinutes: m })}
          hoursLabel="hours"
          minutesLabel="minutes"
        />

        {value.redownloadAfterMinutes.trim() !== '' && (
          <div className="help" aria-live="polite">{redownloadMinutesHelp}</div>
        ) || <div className="help" aria-live="polite">We will not re-download the show after the initial download</div>}

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
