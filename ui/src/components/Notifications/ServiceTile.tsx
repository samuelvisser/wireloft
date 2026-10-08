const PALETTE = ['#2563eb', '#7c3aed', '#db2777', '#ea580c', '#059669', '#0891b2', '#4f46e5', '#b45309']

function colorFor(name: string): string {
    let hash = 0
    for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
    return PALETTE[hash % PALETTE.length]
}

/** A coloured initial that identifies a notification service without shipping 150 logos. */
export default function ServiceTile({name, size = 'md'}: {name: string; size?: 'sm' | 'md'}) {
    return (
        <span
            className={`notif-tile notif-tile--${size}`}
            style={{backgroundColor: colorFor(name)}}
            aria-hidden="true"
        >
            {name.trim().charAt(0).toUpperCase() || '?'}
        </span>
    )
}
