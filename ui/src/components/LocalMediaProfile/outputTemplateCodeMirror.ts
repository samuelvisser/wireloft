import {HighlightStyle, syntaxHighlighting} from '@codemirror/language'
import {jinja} from '@codemirror/lang-jinja'
import {tags} from '@lezer/highlight'

export const outputTemplateHighlightStyle = HighlightStyle.define([
    {tag: tags.brace, class: 'cm-jinja-brace'},
    {
        tag: [tags.keyword, tags.controlKeyword, tags.definitionKeyword, tags.operatorKeyword],
        class: 'cm-jinja-keyword',
    },
    {
        tag: [tags.variableName, tags.propertyName, tags.special(tags.variableName)],
        class: 'cm-jinja-variable',
    },
    {tag: tags.string, class: 'cm-jinja-string'},
    {tag: [tags.number, tags.bool], class: 'cm-jinja-literal'},
    {
        tag: [tags.operator, tags.arithmeticOperator, tags.logicOperator, tags.compareOperator],
        class: 'cm-jinja-operator',
    },
    {tag: tags.comment, class: 'cm-jinja-comment'},
    {tag: tags.blockComment, class: 'cm-jinja-comment'},
])

export const outputTemplateSyntaxExtensions = [
    jinja(),
    syntaxHighlighting(outputTemplateHighlightStyle),
]
