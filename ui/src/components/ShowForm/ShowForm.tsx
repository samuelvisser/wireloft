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

type Props = {
  value: ShowFormValue
  onChange: (value: ShowFormValue) => void
}

export default function ShowForm({ value, onChange }: Props) {

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


    </>
  )
}
