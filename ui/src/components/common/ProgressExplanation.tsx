import {useCallback, useEffect, useId, useLayoutEffect, useRef, useState} from 'react'
import {createPortal} from 'react-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import './ProgressVisual.css'
import {faIcon} from '../../icons/faIcon'

type PopoverPosition = {
    top: number
    left: number
}

const POPOVER_GAP = 6
const VIEWPORT_GUTTER = 8
const POPOVER_WIDTH = 260

export default function ProgressExplanation({detail, buttonClassName = 'icon-btn'}: {
    detail: string
    buttonClassName?: string
}) {
    const [open, setOpen] = useState(false)
    const [position, setPosition] = useState<PopoverPosition>({top: 0, left: 0})
    const id = useId()
    const triggerRef = useRef<HTMLButtonElement>(null)
    const popoverRef = useRef<HTMLSpanElement>(null)

    const positionPopover = useCallback(() => {
        const trigger = triggerRef.current
        const popover = popoverRef.current
        if (!trigger || !popover) return

        const triggerRect = trigger.getBoundingClientRect()
        const width = Math.min(POPOVER_WIDTH, window.innerWidth - VIEWPORT_GUTTER * 2)
        const left = Math.max(
            VIEWPORT_GUTTER,
            Math.min(triggerRect.right - width, window.innerWidth - width - VIEWPORT_GUTTER),
        )

        const below = triggerRect.bottom + POPOVER_GAP
        const above = triggerRect.top - popover.offsetHeight - POPOVER_GAP
        const top = below + popover.offsetHeight <= window.innerHeight - VIEWPORT_GUTTER || above < VIEWPORT_GUTTER
            ? below
            : above

        setPosition({top, left})
    }, [])

    useLayoutEffect(() => {
        if (open) positionPopover()
    }, [detail, open, positionPopover])

    useEffect(() => {
        if (!open) return

        const closeOnOutsidePointer = (event: PointerEvent) => {
            const target = event.target
            if (!(target instanceof Node)) return
            if (triggerRef.current?.contains(target) || popoverRef.current?.contains(target)) return
            setOpen(false)
        }
        const closeOnEscape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setOpen(false)
        }

        document.addEventListener('pointerdown', closeOnOutsidePointer)
        document.addEventListener('keydown', closeOnEscape)
        window.addEventListener('resize', positionPopover)
        window.addEventListener('scroll', positionPopover, true)
        return () => {
            document.removeEventListener('pointerdown', closeOnOutsidePointer)
            document.removeEventListener('keydown', closeOnEscape)
            window.removeEventListener('resize', positionPopover)
            window.removeEventListener('scroll', positionPopover, true)
        }
    }, [open, positionPopover])

    const popover = open && typeof document !== 'undefined'
        ? createPortal(
            <span
                id={id}
                ref={popoverRef}
                className="wl-progress-explanation-text"
                role="note"
                style={{top: position.top, left: position.left}}
            >
                {detail}
            </span>,
            document.body,
        )
        : null

    return <span className="wl-progress-explanation">
        <button
            ref={triggerRef}
            type="button"
            className={buttonClassName}
            aria-label="Progress details"
            aria-expanded={open}
            aria-controls={id}
            onClick={event => {
                event.stopPropagation()
                setOpen(value => !value)
            }}
        >
            <FontAwesomeIcon icon={faIcon('fas', 'circle-info')}/>
        </button>
        {popover}
    </span>
}
