import { useEffect, useMemo } from 'react'
import DailywireShowCard from './DailywireShowCard'
import ReadMore from '../../utils/ReadMore'
import { useDailywireShow } from '../../lib/queries'
import Switch from 'react-switch'
import { z } from 'zod';

type Props = {
  value: DownloadProfileFormValue
  onChange: (v: DownloadProfileFormValue) => void
  onBack: () => void
  onFinish: () => void
  onCancel: () => void
  slug?: string
}

const DownloadProfileSchema = z.object({
  enableProfile: z.boolean(),
  downloadWithCountdown: z.boolean(),
  redownloadFinal: z.boolean(),
  downloadDaysInPast: z.number().min(0),
  deleteOlderEpisodes: z.boolean(),
})

type DownloadProfile = z.infer<typeof DownloadProfileSchema>



export type DownloadProfileFormValue = {
  enableProfile: boolean
  downloadWithCountdown: boolean
  redownloadFinal: boolean
  downloadDaysInPast: number
  deleteOlderEpisodes: boolean
}

export default function DownloadProfileStep({ value, onChange, onBack, onFinish, onCancel, slug }: Props) {
  const dw = useDailywireShow(slug)

  // Determine show type: only show countdown controls for podcasts
  const isPodcast = useMemo(() => {
    const anyData: any = dw.data
    const v = (anyData?.probableShowType ?? anyData?.probable_show_type) as string | undefined
    return v === 'podcast'
  }, [dw.data])

  // Ensure redownloadFinal resets if downloadWithCountdown is turned off
  useEffect(() => {
    if (!value.downloadWithCountdown && value.redownloadFinal) {
      onChange({ ...value, redownloadFinal: false })
    }
  }, [value.downloadWithCountdown])

  const oldestDateText = useMemo(() => {
    const days = Number.isFinite(value.downloadDaysInPast) ? value.downloadDaysInPast : 0
    if (!days || days <= 0) return null
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    d.setDate(d.getDate() - days)
    // Format YYYY-MM-DD
    const yyyy = d.getFullYear()
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    return `${yyyy}-${mm}-${dd}`
  }, [value.downloadDaysInPast])

  return (
    <div className="wizard-with-aside">
      <div className="wizard-main">
        <div className="form form-fluid">
          <div className="form-row">
            <label htmlFor="enable-profile">Enable download profile</label>
            <Switch
              id="enable-profile"
              checked={value.enableProfile}
              onChange={(checked) => onChange({ ...value, enableProfile: checked })}
              onColor="#0ea5e9"
              offColor="#d1d5db"
              uncheckedIcon={false}
              checkedIcon={false}
            />
            <div className="help">Enables downloads for this show</div>
          </div>

          {isPodcast && (
            <div className="form-row">
              <label htmlFor="with-countdown">Download with countdown</label>
              <Switch
                id="with-countdown"
                checked={value.downloadWithCountdown}
                onChange={(checked) => onChange({ ...value, downloadWithCountdown: checked })}
                onColor="#0ea5e9"
                offColor="#d1d5db"
                uncheckedIcon={false}
                checkedIcon={false}
              />
              <div className="help">
                <ReadMore summary={<span>What does this mean?</span>}>
                  Some DailyWire podcast episodes appear with a countdown timer before the final media is available. Enabling this option will download the episode while the countdown is still present, which is useful if you want to start processing early. If enabled, you may also choose to re-download the final version after the countdown disappears.
                </ReadMore>
              </div>
            </div>
          )}

          {isPodcast && value.downloadWithCountdown && (
            <div className="form-row">
              <label htmlFor="redownload-final">Redownload final version</label>
              <Switch
                id="redownload-final"
                checked={value.redownloadFinal}
                onChange={(checked) => onChange({ ...value, redownloadFinal: checked })}
                onColor="#0ea5e9"
                offColor="#d1d5db"
                uncheckedIcon={false}
                checkedIcon={false}
              />
              <div className="help">Whether to redownload the episode once the countdown has been removed</div>
            </div>
          )}

          <div className="form-row">
            <label htmlFor="days-in-past">Download days in past</label>
            <input
              id="days-in-past"
              className="input"
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={value.downloadDaysInPast}
              onChange={(e) => {
                const next = e.target.value === '' ? 0 : Math.max(0, Math.floor(Number(e.target.value)))
                onChange({ ...value, downloadDaysInPast: Number.isFinite(next) ? next : 0 })
              }}
            />
            <div className="help">
              Amount of days in the past the show should be downloaded.
              {oldestDateText ? (
                <>
                  {' '}Oldest date that would be downloaded: <strong>{oldestDateText}</strong>
                </>
              ) : null}
            </div>
          </div>

          {value.downloadDaysInPast > 0 && (
            <div className="form-row">
              <label htmlFor="delete-older">Delete older episodes</label>
              <Switch
                id="delete-older"
                checked={value.deleteOlderEpisodes}
                onChange={(checked) => onChange({ ...value, deleteOlderEpisodes: checked })}
                onColor="#0ea5e9"
                offColor="#d1d5db"
                uncheckedIcon={false}
                checkedIcon={false}
              />
              <div className="help">Whether to delete episodes older than above date</div>
            </div>
          )}

          <div className="actions">
            <button type="button" className="btn" onClick={onBack}>Back</button>
            <button type="button" className="btn btn-primary" onClick={onFinish}>Finish</button>
            <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          </div>
        </div>
      </div>

      {slug ? (
        <aside className="wizard-aside" aria-label="Selected show details">
          <DailywireShowCard slug={slug} />
        </aside>
      ) : null}
    </div>
  )
}
