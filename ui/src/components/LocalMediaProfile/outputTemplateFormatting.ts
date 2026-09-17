type TemplateToken = {
    type: 'text' | 'expression' | 'statement' | 'comment'
    value: string
}

const BLOCK_OPENERS = new Set([
    'if',
    'for',
    'block',
    'macro',
    'call',
    'filter',
    'with',
    'raw',
    'autoescape',
])

const BLOCK_BRANCHES = new Set(['else', 'elif'])

export function compactOutputTemplate(value: string): string {
    return value.replace(/^\t+/, '').replace(/\r?\n\t*/g, '')
}

function tokenizeTemplate(template: string): TemplateToken[] {
    const tokens: TemplateToken[] = []
    let cursor = 0

    while (cursor < template.length) {
        const candidates = [
            {start: '{{', end: '}}', type: 'expression' as const},
            {start: '{%', end: '%}', type: 'statement' as const},
            {start: '{#', end: '#}', type: 'comment' as const},
        ]
            .map((candidate) => ({...candidate, index: template.indexOf(candidate.start, cursor)}))
            .filter(({index}) => index >= 0)
            .sort((left, right) => left.index - right.index)

        const next = candidates[0]
        if (!next) {
            tokens.push({type: 'text', value: template.slice(cursor)})
            break
        }

        if (next.index > cursor) {
            tokens.push({type: 'text', value: template.slice(cursor, next.index)})
        }

        const endIndex = template.indexOf(next.end, next.index + next.start.length)
        if (endIndex < 0) {
            tokens.push({type: 'text', value: template.slice(next.index)})
            break
        }

        const tokenEnd = endIndex + next.end.length
        tokens.push({type: next.type, value: template.slice(next.index, tokenEnd)})
        cursor = tokenEnd
    }

    return tokens
}

function statementKeyword(statement: string): string {
    return statement.slice(2, -2).trim().match(/^([A-Za-z_][A-Za-z0-9_]*)/)?.[1] ?? ''
}

function opensBlock(statement: string, keyword: string): boolean {
    if (BLOCK_OPENERS.has(keyword)) return true
    if (keyword !== 'set') return false

    const body = statement.slice(2, -2).trim().slice('set'.length).trimStart()
    return !body.includes('=')
}

export function formatOutputTemplateForEditor(value: string): string {
    const template = compactOutputTemplate(value)
    if (!template) return ''

    const lines: string[] = []
    let current = ''
    let currentIndent = 0
    let pathDepth = 0
    let blockDepth = 0
    let pathStarted = false

    const defaultIndent = () => pathDepth + blockDepth
    const ensureCurrent = (indent = defaultIndent()) => {
        if (!current) currentIndent = indent
    }
    const append = (text: string, indent = defaultIndent()) => {
        if (!text) return
        ensureCurrent(indent)
        current += text
    }
    const flush = () => {
        if (!current) return
        lines.push(`${'\t'.repeat(Math.max(0, currentIndent))}${current}`)
        current = ''
    }

    const appendText = (text: string) => {
        let cursor = 0
        for (let slash = text.indexOf('/', cursor); slash >= 0; slash = text.indexOf('/', cursor)) {
            append(text.slice(cursor, slash))
            flush()
            if (pathStarted) pathDepth += 1
            else pathStarted = true
            append('/', pathDepth + blockDepth)
            cursor = slash + 1
        }
        append(text.slice(cursor))
    }

    for (const token of tokenizeTemplate(template)) {
        if (token.type === 'text') {
            appendText(token.value)
            continue
        }

        if (token.type === 'expression' || token.type === 'comment') {
            append(token.value)
            continue
        }

        const keyword = statementKeyword(token.value)
        const isClosing = keyword.startsWith('end')
        const isBranch = BLOCK_BRANCHES.has(keyword)
        const isOpening = opensBlock(token.value, keyword)

        flush()
        if (isClosing) blockDepth = Math.max(0, blockDepth - 1)

        const statementIndent = pathDepth + (isBranch ? Math.max(0, blockDepth - 1) : blockDepth)
        append(token.value, statementIndent)
        flush()

        if (isOpening) blockDepth += 1
    }

    flush()
    return lines.join('\n')
}

export function editorPositionForCompactOffset(formatted: string, compactOffset: number): number {
    if (compactOffset <= 0) return 0

    let compactPosition = 0
    for (let index = 0; index < formatted.length; index += 1) {
        if (formatted[index] === '\n') {
            while (formatted[index + 1] === '\t') index += 1
            continue
        }

        compactPosition += 1
        if (compactPosition >= compactOffset) return index + 1
    }

    return formatted.length
}
