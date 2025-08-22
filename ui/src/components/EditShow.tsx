import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ShowForm, { ShowFormValue } from './ShowForm'

// Local fallback profiles (to populate select)
const fallbackProfiles = [
  { id: 'p1', name: 'Default 1080p' },
  { id: 'p2', name: 'Mobile 720p' },
]

type RouteParams = { id?: string }

type FormState = {
  url: string
  name: string
  author: string
  mediaProfileId: string
  downloadMedia: boolean
  downloadDays: string // keep as string to allow empty input
  deleteOlder: boolean
  titleFilter: string
}


function defaultShowData(id?: string): { url: string; name: string; author: string } | undefined {
  if (!id) return undefined
  const map: Record<string, { name: string; author: string }> = {
    'the-ben-shapiro-show': { name: 'The Ben Shapiro Show', author: 'Ben Shapiro' },
    'the-matt-walsh-show': { name: 'The Matt Walsh Show', author: 'Matt Walsh' },
    'ben-after-dark': { name: 'Ben After Dark', author: 'Ben Shapiro' },
  }
  const found = map[id]
  if (!found) return { url: `https://www.dailywire.com/show/${id}`, name: id, author: '' }
  return { url: `https://www.dailywire.com/show/${id}`, name: found.name, author: found.author }
}

export default function EditShow() {
  const { id } = useParams<RouteParams>()
  const navigate = useNavigate()

  const [form, setForm] = useState<FormState>(() => {
    const base = defaultShowData(id)
    return {
      url: base?.url ?? '',
      name: base?.name ?? '',
      author: base?.author ?? '',
      mediaProfileId: 'p1',
      downloadMedia: true,
      downloadDays: '',
      deleteOlder: false,
      titleFilter: '',
    }
  })

  const onCancel = () => navigate(`/show/${id ?? ''}`)
  const onSave = () => {
    // Placeholder save behavior
    alert('Save show changes:\n' + JSON.stringify({ id, ...form }, null, 2))
    navigate(`/show/${id ?? ''}`)
  }

  if (!id) {
    return (
      <section className="view" aria-labelledby="edit-show-title">
        <div className="view-header">
          <h1 id="edit-show-title">Edit show</h1>
        </div>
        <p>Show not found.</p>
        <div className="actions" style={{ marginTop: 12 }}>
          <button type="button" className="btn" onClick={() => navigate('/')}>Back</button>
        </div>
      </section>
    )
  }

  return (
    <section className="view" aria-labelledby="edit-show-title">
      <div className="view-header">
        <h1 id="edit-show-title">Edit show</h1>
      </div>

      <form className="form" onSubmit={(e) => e.preventDefault()}>
        <div className="form-row">
          <label htmlFor="show-url">Show URL</label>
          <input
            id="show-url"
            className="input"
            type="url"
            inputMode="url"
            placeholder="https://www.dailywire.com/show/the-ben-shapiro-show"
            value={form.url}
            onChange={(e) => setForm({ ...form, url: e.target.value })}
          />
        </div>



        <div className="form-row">
          <label htmlFor="media-profile">Media Profile</label>
          <select
            id="media-profile"
            className="input"
            value={form.mediaProfileId}
            onChange={(e) => setForm({ ...form, mediaProfileId: e.target.value })}
          >
            {fallbackProfiles.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        <ShowForm
          value={{
            name: form.name,
            author: form.author,
            downloadMedia: form.downloadMedia,
            downloadDays: form.downloadDays,
            deleteOlder: form.deleteOlder,
            titleFilter: form.titleFilter,
          }}
          onChange={(v: ShowFormValue) =>
            setForm({
              ...form,
              name: v.name,
              author: v.author,
              downloadMedia: v.downloadMedia,
              downloadDays: v.downloadDays,
              deleteOlder: v.deleteOlder,
              titleFilter: v.titleFilter,
            })
          }
        />

        <div className="actions">
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={onSave}>Save changes</button>
        </div>
      </form>
    </section>
  )
}
