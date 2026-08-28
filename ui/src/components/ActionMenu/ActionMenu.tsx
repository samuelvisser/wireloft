import {useEffect, useId, useRef, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import './ActionMenu.css'

export type ActionMenuItem = {
    label: string
    icon?: any
    onSelect: () => void
    disabled?: boolean
    tone?: 'default' | 'danger'
    separatorBefore?: boolean
}

type Props = {
    label?: string
    items: ActionMenuItem[]
    className?: string
}

export default function ActionMenu({label = 'Actions', items, className = ''}: Props) {
    const [open, setOpen] = useState(false)
    const rootRef = useRef<HTMLDivElement>(null)
    const triggerRef = useRef<HTMLButtonElement>(null)
    const menuId = useId()

    useEffect(() => {
        if (!open) return

        const onPointerDown = (event: PointerEvent) => {
            const root = rootRef.current
            if (root && !root.contains(event.target as Node)) setOpen(false)
        }

        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key !== 'Escape') return
            setOpen(false)
            triggerRef.current?.focus()
        }

        document.addEventListener('pointerdown', onPointerDown)
        document.addEventListener('keydown', onKeyDown)
        return () => {
            document.removeEventListener('pointerdown', onPointerDown)
            document.removeEventListener('keydown', onKeyDown)
        }
    }, [open])

    const selectItem = (item: ActionMenuItem) => {
        if (item.disabled) return
        setOpen(false)
        item.onSelect()
    }

    return (
        <div ref={rootRef} className={`action-menu${open ? ' is-open' : ''}${className ? ` ${className}` : ''}`}>
            <button
                ref={triggerRef}
                type="button"
                className="btn btn-secondary action-menu-trigger"
                aria-haspopup="menu"
                aria-expanded={open}
                aria-controls={menuId}
                onClick={() => setOpen((value) => !value)}
            >
                <span>{label}</span>
                <FontAwesomeIcon className="action-menu-caret" icon={['fas', 'chevron-down'] as any} aria-hidden="true"/>
            </button>

            {open && (
                <>
                    <div className="action-menu-backdrop" aria-hidden="true" onClick={() => setOpen(false)}/>
                    <div id={menuId} className="action-menu-popover" role="menu" aria-label={label}>
                        {items.map((item, index) => (
                            <div key={`${item.label}-${index}`} className="action-menu-entry">
                                {item.separatorBefore && <div className="action-menu-separator" role="separator"/>}
                                <button
                                    type="button"
                                    role="menuitem"
                                    className={`action-menu-item${item.tone === 'danger' ? ' is-danger' : ''}`}
                                    disabled={item.disabled}
                                    onClick={() => selectItem(item)}
                                >
                                    {item.icon && (
                                        <FontAwesomeIcon className="action-menu-item-icon" icon={item.icon} aria-hidden="true"/>
                                    )}
                                    <span>{item.label}</span>
                                </button>
                            </div>
                        ))}
                    </div>
                </>
            )}
        </div>
    )
}
