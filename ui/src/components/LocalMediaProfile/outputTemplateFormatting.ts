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

function linePrefix(value: string, index: number): string {
    const lineStart = value.lastIndexOf('\n', index - 1) + 1
    return value.slice(lineStart, index)
}

function isPresentationWhitespace(value: string, index: number): boolean {
    const character = value[index]
    if (character === '\n' || character === '\r') return true
    if (character !== ' ' && character !== '\t') return false

    const prefix = linePrefix(value, index)
    if (/^[\t ]*$/.test(prefix)) return true

    // Keep a space immediately after a path separator presentation-only so it
    // can never accidentally become part of the saved output path.
    return character === ' ' && /^[\t ]*\/ *$/.test(prefix)
}

export function compactOutputTemplate(value: string): string {
    let compact = ''
    for (let index = 0; index < value.length; index += 1) {
        if (!isPresentationWhitespace(value, index)) compact += value[index]
    }
    return compact
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
    const blockIndents: number[] = []
    let current = ''
    let currentIndent = 0
    let pathStarted = false
    let separateLeadingStatementsFromPath = false

    const contentIndent = () => {
        const blockIndent = blockIndents[blockIndents.length - 1]
        return blockIndent === undefined ? 0 : blockIndent + 1
    }
    const ensureCurrent = (indent = contentIndent()) => {
        if (!current) currentIndent = indent
    }
    const append = (text: string, indent = contentIndent()) => {
        if (!text) return
        ensureCurrent(indent)
        current += text
    }
    const flush = () => {
        if (!current) return
        lines.push(`${'\t'.repeat(Math.max(0, currentIndent))}${current}`)
        current = ''
    }
    const startPathLine = () => {
        if (!pathStarted && separateLeadingStatementsFromPath && lines[lines.length - 1] !== '') {
            lines.push('')
        }
        pathStarted = true
        append('/', contentIndent())
    }

    const appendText = (text: string) => {
        let cursor = 0
        for (let slash = text.indexOf('/', cursor); slash >= 0; slash = text.indexOf('/', cursor)) {
            append(text.slice(cursor, slash))
            flush()
            startPathLine()
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

        let statementIndent: number
        if (isClosing) {
            statementIndent = blockIndents.pop() ?? 0
        } else if (isBranch) {
            statementIndent = blockIndents[blockIndents.length - 1] ?? (pathStarted ? 1 : 0)
        } else if (isOpening) {
            statementIndent = blockIndents.length > 0 ? contentIndent() : (pathStarted ? 1 : 0)
        } else {
            statementIndent = contentIndent()
        }

        append(token.value, statementIndent)
        flush()

        if (isOpening) blockIndents.push(statementIndent)
        if (!pathStarted && !isOpening && !isClosing && !isBranch && blockIndents.length === 0) {
            separateLeadingStatementsFromPath = true
        }
    }

    flush()
    return lines.join('\n')
}

export function editorPositionForCompactOffset(formatted: string, compactOffset: number): number {
    if (compactOffset <= 0) return 0

    let compactPosition = 0
    for (let index = 0; index < formatted.length; index += 1) {
        if (isPresentationWhitespace(formatted, index)) continue

        compactPosition += 1
        if (compactPosition >= compactOffset) {
            let editorPosition = index + 1
            while (
                editorPosition < formatted.length
                && formatted[editorPosition] !== '\n'
                && formatted[editorPosition] !== '\r'
                && isPresentationWhitespace(formatted, editorPosition)
            ) {
                editorPosition += 1
            }
            return editorPosition
        }
    }

    return formatted.length
}
