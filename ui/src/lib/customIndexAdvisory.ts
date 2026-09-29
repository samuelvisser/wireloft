import {parseOutputTemplate, type OutputTemplateNode} from '../components/LocalMediaProfile/outputTemplateFormatting'

export type IndexDefinition = {key: string}

/** Reuse the editor's tag tree: comments, raw text and quoted strings are not code. */
export function customIndexReferences(template: string): string[] {
    const keys = new Set<string>()
    function inspect(source: string) {
        const tokens = source.match(/'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*|[^\s]/g) ?? []
        for (let i = 1; i < tokens.length; i += 1) {
            if (tokens[i] !== 'custom_index' || tokens[i - 1] !== '|') continue
            let left = i - 2
            let parentheses = 0
            while (tokens[left] === ')') {
                parentheses += 1
                left -= 1
            }
            const literal = tokens[left] ?? ''
            if (!/^(['"])[a-z_][a-z0-9_-]*\1$/.test(literal)) continue
            // Parentheses around a literal are fine, but a call or an expression
            // ending in that literal is not a literal custom_index key.
            let start = left
            while (parentheses > 0 && tokens[start - 1] === '(') {
                start -= 1
                parentheses -= 1
            }
            if (parentheses > 0) continue
            if (start < left && /^[A-Za-z0-9_\])]/.test(tokens[start - 1] ?? '')) continue
            keys.add(literal.slice(1, -1))
        }
    }
    let inRaw = false
    function visit(items: OutputTemplateNode[]) {
        for (const item of items) {
            if (item.type === 'statement') {
                const rawTag = /^{%[-+]?\s*(raw|endraw)\s*[-+]?%}$/.exec(item.source)
                if (rawTag) {
                    inRaw = rawTag[1] === 'raw'
                    continue
                }
            }
            if (!inRaw && (item.type === 'expression' || item.type === 'statement')) inspect(item.source)
            if (item.type !== 'block' || item.keyword === 'raw') continue
            if (!inRaw) inspect(item.opener.source)
            visit(item.body)
            for (const branch of item.branches) {
                if (!inRaw) inspect(branch.statement.source)
                visit(branch.children)
            }
        }
    }
    visit(parseOutputTemplate(template).children)
    return [...keys].sort()
}

export function customIndexAdvisoryRequest(template: string, definitions: IndexDefinition[]): string | null {
    if (!template || template.length > 4096) return null
    const keys = [...new Set(definitions.map(({key}) => key))].sort()
    if (!customIndexReferences(template).some((key) => keys.includes(key))) return null
    return JSON.stringify({outputTemplate: template, indexingValueKeys: keys})
}
