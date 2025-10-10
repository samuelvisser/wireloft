import DailywireAuthCard from '../components/DailywireAuth/DailywireAuthCard'

export default function SettingsPage() {
  return (
    <section className="view" aria-labelledby="settings-title">
      <h1 id="settings-title">Settings</h1>
      <p>Adjust application settings.</p>
      <div style={{marginTop: 16}}>
        <DailywireAuthCard />
      </div>
    </section>
  )
}
