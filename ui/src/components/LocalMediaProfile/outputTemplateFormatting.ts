// Frontend-only syntax tree for the output-template editor. The form/API value stays compact Jinja;
// editor whitespace is produced only by the editor renderer and never sent to the backend.
export type OutputTemplateSourceMode = 'compact' | 'editor'

type TextNode = {
    type: 'text'
    value: string
}

type JinjaExpressionNode = {
    type: 'expression'
    source: string
    complete: boolean
}

type JinjaCommentNode = {
    type: 'comment'
    source: string
    complete: boolean
}

export type JinjaStatementNode = {
    type: 'statement'
    source: string
    keyword: string
    complete: boolean
}

export type JinjaBranchNode = {
    statement: JinjaStatementNode
    children: OutputTemplateNode[]
}

export type JinjaBlockNode = {
    type: 'block'
    keyword: string
    expectedCloser: string
    opener: JinjaStatementNode
    body: OutputTemplateNode[]
    branches: JinjaBranchNode[]
    closer?: JinjaStatementNode
}

export type OutputTemplateNode =
    | TextNode
    | JinjaExpressionNode
    | JinjaCommentNode
    | JinjaStatementNode
    | JinjaBlockNode

export type OutputTemplateAst = {
    type: 'template'
    children: OutputTemplateNode[]
    openBlocks: JinjaBlockNode[]
}

export type JinjaStatementInfo = {
    keyword: string
    opensBlock: boolean
    expectedCloser?: string
    isBranch: boolean
    isCloser: boolean
}

export type EditorTemplateRender = {
    value: string
    compactToEditor: number[]
}

type TemplateToken =
    | {type: 'text'; source: string}
    | {type: 'expression' | 'statement' | 'comment'; source: string; complete: boolean}

type BlockFrame = {
    block: JinjaBlockNode
    activeChildren: OutputTemplateNode[]
}

const BLOCK_CLOSERS: Record<string, string> = {
    if: 'endif',
    for: 'endfor',
    block: 'endblock',
    macro: 'endmacro',
    call: 'endcall',
    filter: 'endfilter',
    with: 'endwith',
    raw: 'endraw',
    autoescape: 'endautoescape',
}

const BRANCH_KEYWORDS = new Set(['elif', 'else'])

function statementKeyword(source: string): string {
    const body = source.startsWith('{%') ? source.slice(2, source.endsWith('%}') ? -2 : undefined) : source
    return body.trim().match(/^([A-Za-z_][A-Za-z0-9_]*)/)?.[1] ?? ''
}

export function analyzeJinjaStatement(source: string): JinjaStatementInfo {
    const keyword = statementKeyword(source)
    let expectedCloser = BLOCK_CLOSERS[keyword]

    if (keyword === 'set') {
        const body = source.startsWith('{%') ? source.slice(2, source.endsWith('%}') ? -2 : undefined) : source
        const assignment = body.trim().slice('set'.length).trimStart()
        if (!assignment.includes('=')) expectedCloser = 'endset'
    }

    return {
        keyword,
        opensBlock: !!expectedCloser,
        expectedCloser,
        isBranch: BRANCH_KEYWORDS.has(keyword),
        isCloser: keyword.startsWith('end'),
    }
}

function normalizeEditorSource(value: string): string {
    let canonical = ''
    let index = 0
    let lineStart = true
    let jinjaEnd: '}}' | '%}' | '#}' | null = null
    let quote: "'" | '"' | null = null
    let escaped = false

    while (index < value.length) {
        const character = value[index]

        if (character === '\r' || character === '\n') {
            if (character === '\r' && value[index + 1] === '\n') index += 1
            if (jinjaEnd && canonical && !/\s$/.test(canonical)) canonical += ' '
            lineStart = true
            index += 1
            continue
        }

        if (lineStart && (character === ' ' || character === '\t')) {
            index += 1
            continue
        }
        lineStart = false

        const pair = value.slice(index, index + 2)
        if (!jinjaEnd) {
            const end = pair === '{{' ? '}}' : pair === '{%' ? '%}' : pair === '{#' ? '#}' : null
            if (end) {
                canonical += pair
                jinjaEnd = end
                quote = null
                escaped = false
                index += 2
                continue
            }

            canonical += character
            index += 1
            continue
        }

        if (jinjaEnd === '#}') {
            if (pair === '#}') {
                canonical += pair
                jinjaEnd = null
                index += 2
                continue
            }
            canonical += character
            index += 1
            continue
        }

        if (quote) {
            canonical += character
            if (escaped) {
                escaped = false
            } else if (character === '\\') {
                escaped = true
            } else if (character === quote) {
                quote = null
            }
            index += 1
            continue
        }

        if (character === "'" || character === '"') {
            quote = character
            canonical += character
            index += 1
            continue
        }

        if (pair === jinjaEnd) {
            canonical += pair
            jinjaEnd = null
            index += 2
            continue
        }

        canonical += character
        index += 1
    }

    return canonical
}

function findTagEnd(source: string, start: number, endDelimiter: '}}' | '%}' | '#}'): number {
    if (endDelimiter === '#}') return source.indexOf(endDelimiter, start + 2)

    let quote: "'" | '"' | null = null
    let escaped = false
    for (let index = start + 2; index < source.length - 1; index += 1) {
        const character = source[index]
        if (quote) {
            if (escaped) {
                escaped = false
            } else if (character === '\\') {
                escaped = true
            } else if (character === quote) {
                quote = null
            }
            continue
        }

        if (character === "'" || character === '"') {
            quote = character
            continue
        }

        if (source.slice(index, index + 2) === endDelimiter) return index
    }
    return -1
}

function nextJinjaStart(source: string, cursor: number) {
    return [
        {start: '{{', end: '}}' as const, type: 'expression' as const},
        {start: '{%', end: '%}' as const, type: 'statement' as const},
        {start: '{#', end: '#}' as const, type: 'comment' as const},
    ]
        .map((candidate) => ({...candidate, index: source.indexOf(candidate.start, cursor)}))
        .filter(({index}) => index >= 0)
        .sort((left, right) => left.index - right.index)[0]
}

function tokenizeTemplate(source: string): TemplateToken[] {
    const tokens: TemplateToken[] = []
    let cursor = 0
    let raw = false

    while (cursor < source.length) {
        if (raw) {
            const endRaw = /{%\s*endraw\s*%}/g
            endRaw.lastIndex = cursor
            const match = endRaw.exec(source)
            if (!match) {
                tokens.push({type: 'text', source: source.slice(cursor)})
                break
            }
            if (match.index > cursor) tokens.push({type: 'text', source: source.slice(cursor, match.index)})
            tokens.push({type: 'statement', source: match[0], complete: true})
            cursor = match.index + match[0].length
            raw = false
            continue
        }

        const next = nextJinjaStart(source, cursor)
        if (!next) {
            tokens.push({type: 'text', source: source.slice(cursor)})
            break
        }

        if (next.index > cursor) tokens.push({type: 'text', source: source.slice(cursor, next.index)})

        const endIndex = findTagEnd(source, next.index, next.end)
        if (endIndex < 0) {
            const token: TemplateToken = {
                type: next.type,
                source: source.slice(next.index),
                complete: false,
            }
            tokens.push(token)
            break
        }

        const tokenEnd = endIndex + next.end.length
        const token: TemplateToken = {
            type: next.type,
            source: source.slice(next.index, tokenEnd),
            complete: true,
        }
        tokens.push(token)
        cursor = tokenEnd
        if (next.type === 'statement' && statementKeyword(token.source) === 'raw') raw = true
    }

    return tokens
}

function branchBelongsToBlock(keyword: string, block: JinjaBlockNode): boolean {
    if (keyword === 'elif') return block.keyword === 'if'
    if (keyword === 'else') return block.keyword === 'if' || block.keyword === 'for'
    return false
}

export function parseOutputTemplate(value: string, mode: OutputTemplateSourceMode = 'compact'): OutputTemplateAst {
    const source = mode === 'editor' ? normalizeEditorSource(value) : value
    const root: OutputTemplateAst = {type: 'template', children: [], openBlocks: []}
    const stack: BlockFrame[] = []
    let currentChildren = root.children

    for (const token of tokenizeTemplate(source)) {
        if (token.type === 'text') {
            currentChildren.push({type: 'text', value: token.source})
            continue
        }
        if (token.type === 'expression') {
            currentChildren.push({type: 'expression', source: token.source, complete: token.complete})
            continue
        }
        if (token.type === 'comment') {
            currentChildren.push({type: 'comment', source: token.source, complete: token.complete})
            continue
        }

        const info = analyzeJinjaStatement(token.source)
        const statement: JinjaStatementNode = {
            type: 'statement',
            source: token.source,
            keyword: info.keyword,
            complete: token.complete,
        }

        if (!token.complete) {
            currentChildren.push(statement)
            continue
        }

        if (info.opensBlock && info.expectedCloser) {
            const block: JinjaBlockNode = {
                type: 'block',
                keyword: info.keyword,
                expectedCloser: info.expectedCloser,
                opener: statement,
                body: [],
                branches: [],
            }
            currentChildren.push(block)
            const frame: BlockFrame = {block, activeChildren: block.body}
            stack.push(frame)
            currentChildren = frame.activeChildren
            continue
        }

        const currentFrame = stack[stack.length - 1]
        if (info.isBranch && currentFrame && branchBelongsToBlock(info.keyword, currentFrame.block)) {
            const branch: JinjaBranchNode = {statement, children: []}
            currentFrame.block.branches.push(branch)
            currentFrame.activeChildren = branch.children
            currentChildren = branch.children
            continue
        }

        if (info.isCloser && currentFrame && currentFrame.block.expectedCloser === info.keyword) {
            currentFrame.block.closer = statement
            stack.pop()
            currentChildren = stack.length ? stack[stack.length - 1].activeChildren : root.children
            continue
        }

        currentChildren.push(statement)
    }

    root.openBlocks = stack.map(({block}) => block)
    return root
}

function renderCompactNodes(nodes: OutputTemplateNode[]): string {
    return nodes.map((node) => {
        if (node.type === 'text') return node.value
        if (node.type === 'expression' || node.type === 'comment' || node.type === 'statement') return node.source

        return [
            node.opener.source,
            renderCompactNodes(node.body),
            ...node.branches.flatMap((branch) => [branch.statement.source, renderCompactNodes(branch.children)]),
            node.closer?.source ?? '',
        ].join('')
    }).join('')
}

export function renderCompactOutputTemplate(ast: OutputTemplateAst): string {
    return renderCompactNodes(ast.children)
}

function nodeContainsPathStart(node: OutputTemplateNode): boolean {
    if (node.type === 'text') return node.value.includes('/')
    if (node.type !== 'block') return false

    return node.body.some(nodeContainsPathStart)
        || node.branches.some((branch) => branch.children.some(nodeContainsPathStart))
}

function commentLeadsIntoPath(nodes: OutputTemplateNode[], commentIndex: number): boolean {
    for (let index = commentIndex + 1; index < nodes.length; index += 1) {
        const node = nodes[index]
        if (node.type === 'comment') continue
        return nodeContainsPathStart(node)
    }
    return false
}

class EditorRenderer {
    private output = ''
    private compactOffset = 0
    private readonly compactToEditor: number[] = [0]
    private atLineStart = true
    private pathStarted = false
    private leadingLogicBeforePath = false
    private leadingPathComment = false

    private appendPresentation(value: string) {
        if (!value) return
        this.output += value
    }

    private appendSource(value: string, indent: number) {
        if (!value) return
        if (this.atLineStart) {
            this.appendPresentation('\t'.repeat(Math.max(0, indent)))
            this.atLineStart = false
        }
        for (const character of value) {
            this.output += character
            this.compactOffset += 1
            this.compactToEditor[this.compactOffset] = this.output.length
        }
    }

    private breakLine() {
        if (this.atLineStart) return
        this.appendPresentation('\n')
        this.atLineStart = true
    }

    private startPathLine(indent: number) {
        if (!this.pathStarted && this.leadingLogicBeforePath && !this.leadingPathComment && this.output.endsWith('\n')) {
            this.appendPresentation('\n')
        }
        this.pathStarted = true
        this.leadingPathComment = false
        this.appendSource('/', indent)
    }

    private renderText(value: string, indent: number) {
        let cursor = 0
        for (let slash = value.indexOf('/', cursor); slash >= 0; slash = value.indexOf('/', cursor)) {
            this.appendSource(value.slice(cursor, slash), indent)
            this.breakLine()
            this.startPathLine(indent)
            cursor = slash + 1
        }
        this.appendSource(value.slice(cursor), indent)
    }

    private renderComment(source: string, indent: number, leadsIntoPath: boolean) {
        this.breakLine()
        if (!this.pathStarted && leadsIntoPath && this.leadingLogicBeforePath && !this.leadingPathComment) {
            this.appendPresentation('\n')
        }

        const commentIndent = indent > 0 ? indent : (this.pathStarted ? 1 : 0)
        this.appendSource(source, commentIndent)
        this.breakLine()
        if (!this.pathStarted && leadsIntoPath) this.leadingPathComment = true
    }

    private renderBlock(block: JinjaBlockNode, indent: number) {
        this.breakLine()
        const openerIndent = indent > 0 ? indent : (this.pathStarted ? 1 : 0)
        this.appendSource(block.opener.source, openerIndent)
        this.breakLine()
        this.renderNodes(block.body, openerIndent + 1)

        for (const branch of block.branches) {
            this.breakLine()
            this.appendSource(branch.statement.source, openerIndent)
            this.breakLine()
            this.renderNodes(branch.children, openerIndent + 1)
        }

        if (block.closer) {
            this.breakLine()
            this.appendSource(block.closer.source, openerIndent)
            this.breakLine()
        }

        if (!this.pathStarted && indent === 0) this.leadingLogicBeforePath = true
    }

    private renderNodes(nodes: OutputTemplateNode[], indent: number) {
        for (let index = 0; index < nodes.length; index += 1) {
            const node = nodes[index]
            if (node.type === 'text') {
                this.renderText(node.value, indent)
                continue
            }
            if (node.type === 'expression') {
                this.appendSource(node.source, indent)
                continue
            }
            if (node.type === 'comment') {
                this.renderComment(node.source, indent, commentLeadsIntoPath(nodes, index))
                continue
            }
            if (node.type === 'block') {
                this.renderBlock(node, indent)
                continue
            }

            this.breakLine()
            const statementIndent = indent > 0 ? indent : (this.pathStarted ? 1 : 0)
            this.appendSource(node.source, statementIndent)
            this.breakLine()
            if (!this.pathStarted && indent === 0) this.leadingLogicBeforePath = true
        }
    }

    render(ast: OutputTemplateAst): EditorTemplateRender {
        this.renderNodes(ast.children, 0)
        while (this.output.endsWith('\n')) this.output = this.output.slice(0, -1)
        this.compactToEditor[this.compactOffset] = this.output.length
        return {value: this.output, compactToEditor: this.compactToEditor}
    }
}

export function renderEditorOutputTemplate(ast: OutputTemplateAst): EditorTemplateRender {
    return new EditorRenderer().render(ast)
}

export function editorPositionForCompactOffset(rendered: EditorTemplateRender, compactOffset: number): number {
    if (compactOffset <= 0) return rendered.compactToEditor[0] ?? 0
    const clamped = Math.min(compactOffset, rendered.compactToEditor.length - 1)
    return rendered.compactToEditor[clamped] ?? rendered.value.length
}

export function getOpenJinjaBlocks(value: string, editorPosition = value.length): JinjaBlockNode[] {
    return parseOutputTemplate(value.slice(0, Math.max(0, editorPosition)), 'editor').openBlocks
}
