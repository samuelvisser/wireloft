import {useId, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import './ProgressVisual.css'

export default function ProgressExplanation({detail}: {detail: string}) {
    const [open, setOpen] = useState(false)
    const id = useId()
    return <span className="wl-progress-explanation" onKeyDown={event => {if (event.key === 'Escape') setOpen(false)}}>
        <button type="button" className="icon-btn" aria-label="Progress details" aria-expanded={open} aria-controls={id}
                onClick={event => {event.stopPropagation(); setOpen(value => !value)}}>
            <FontAwesomeIcon icon={['fas', 'circle-info']}/>
        </button>
        {open && <span id={id} className="wl-progress-explanation-text" role="note">{detail}</span>}
    </span>
}
