import AddShowPageImpl from '../../components/AddShowPage/AddShowPage'

export type AddShowPageProps = {
  onCancel: () => void
}

export default function AddShowPage({ onCancel }: AddShowPageProps) {
  return (
    <section className="view" aria-labelledby="add-show-title">
      <div className="view-header">
        <h1 id="add-show-title">Add show</h1>
      </div>
      <AddShowPageImpl onCancel={onCancel} />
    </section>
  )
}
