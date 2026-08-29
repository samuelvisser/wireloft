import AddShowPageImpl from '../../components/AddShowPage/AddShowPage'
import {useSearchParams} from 'react-router-dom'

export type AddShowPageProps = {
  onCancel: () => void
}

export default function AddShowPage({ onCancel }: AddShowPageProps) {
  const [params] = useSearchParams()
  const initialUrl = params.get('url') || undefined
  return (
    <section className="view" aria-labelledby="add-show-title">
      <div className="view-header">
        <h1 id="add-show-title">Add show</h1>
      </div>
      <AddShowPageImpl onCancel={onCancel} initialUrl={initialUrl} />
    </section>
  )
}
