import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faGithub } from '@fortawesome/free-brands-svg-icons'

interface FooterProps {
  wrapperClass: string
}

export default function Footer({ wrapperClass }: FooterProps) {
  const handleLogout = async () => {
    const base = (window as any).appConfig?.API_URL || '/api'
    try {
      await fetch(`${base}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch (e) {
      // ignore
    } finally {
      window.location.reload()
    }
  }

  return (
    <footer className={wrapperClass} aria-label="Footer">
      <div className="footer-links">
        <a
          href="https://github.com/samuelvisser/wireloft"
          target="_blank"
          rel="noreferrer"
          className="footer-link"
        >
          <span className="icon" aria-hidden>
            <FontAwesomeIcon icon={faGithub} />
          </span>
          <span>Github</span>
        </a>
        <button
          type="button"
          className="footer-link"
          onClick={handleLogout}
          style={{ background: 'none', border: 'none', width: '100%', textAlign: 'left', cursor: 'pointer' }}
        >
          <span className="icon" aria-hidden>
            <FontAwesomeIcon icon={["fas", "right-from-bracket"]} />
          </span>
          <span>Logout</span>
        </button>
      </div>
      <div className="footer-meta" style={{ textAlign: 'center' }}>
        <span className="version" aria-label="App version" style={{ color: 'gray' }}>
          v{(window as any).appConfig?.APP_VERSION ?? 'Unknown app version'}
        </span>
      </div>
    </footer>
  )
}
