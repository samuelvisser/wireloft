# Custom Index advice in the template editor

WireLoft uses normal Jinja execution for output templates. The editor can now
explain likely mistakes without changing the template's meaning or preventing
an otherwise valid Local Media Profile from being saved.

Each referenced Custom Index has its own warning when appropriate:

- An undefined Indexing Value renders as empty. Add the definition in the current
  form or remove the reference. This remains a warning, not a save error.
- An index that is guaranteed to run for every episode receives an all-episode
  warning. For an extras-only sequence, put the index call inside the condition
  that identifies an extra.
- When the index value reaches the output without conditional uses, the editor
  treats the all-episode numbering as intentional and recommends `episode_index`.
  Unrelated conditions or title-formatting methods do not change this advice.

The advice uses the template and definitions currently in the form, including
unsaved edits. It does not inspect the selected example or scan the episode
library. Preview requests continue independently and never wait for advice.

## Use the existing episode index for show-wide numbering

`episode_index` is WireLoft's stored index for that episode within its show.
It includes all episode types, does not restart for each season or type, and is
not the database row ID or the media-facing `episode_number`.

For example, this unconditional declaration:

```jinja
{% set extra_num = 'extra' | custom_index %}
{% set clean_title = title.replace(' ', '-') %}
/downloads/{{ extra_num }} - {{ clean_title }}.ext
```

can be replaced, after reviewing the suggestion, with:

```jinja
{% set extra_num = (episode_index | int) %}
{% set clean_title = title.replace(' ', '-') %}
/downloads/{{ extra_num }} - {{ clean_title }}.ext
```

Template variables are text. The suggested `int` filter retains the numeric
behavior of a Custom Index for formatting or arithmetic. Unrelated code stays
unchanged. An unused Indexing Value definition can then be removed manually.

The stored episode index is not recalculated by the template and may contain
gaps. It matches an all-episode Custom Index when stored indexes are consecutive
from 1, but the advisory does not promise identical numbers for every library.
Review the example path before saving a replacement.

## Suggested conditional code changes

When an unconditional index declaration flows through a single-use chain of
variables or formatting into an existing conditional string assignment, the
editor can instead suggest a native Jinja set block. For example:

```jinja
{% set is_extra = season_type == 'extra' or episode_type == 'aux' %}
{% set extra_num = 'extra' | custom_index %}
{% set episode_id = 'other' ~ extra_num if is_extra else 'S' ~ season_num ~ 'E' ~ ep_num %}
```

The suggested change removes `extra_num` and replaces the last assignment with:

```jinja
{% set episode_id %}
    {% if is_extra %}
        other{{ 'extra' | custom_index }}
    {% else %}
        S{{ season_num }}E{{ ep_num }}
    {% endif %}
{% endset %}
```

The editor displays readable indentation while retaining its usual compact form
value, so the suggested block does not add whitespace to the actual filename.

Expand **Suggested change** to review the original code and replacement, then
choose **Use suggested change** to update the form. Nothing is applied or saved
automatically. Review the preview before saving: restricting membership can
renumber the participating episodes when Custom Indexes are reconciled.

## Other supported patterns

Advice is not limited to a particular variable name or a set block. Bounded,
unambiguous patterns also include direct and nested `if`/`elif` branches,
inline conditionals, `and`/`or` short-circuiting, closed formatting chains,
and existing captured set or filter blocks. Where a captured string could
change a later filter, numeric operation, or `Undefined` test, the suggestion
keeps the original expression instead.

A uniquely called, locally defined macro can capture an index or receive one
as an eagerly evaluated argument. When the relevant value is used once in a
known conditional branch, the editor can move the call into that branch. Other
macro arguments remain at their original evaluation site. Shared, redefined,
recursive, introspected, or ambiguously scoped macros do not get this refactor.

Literal list and dictionary selection can also be made conditional. For a named
table, the suggestion keeps the table and its other entries at the original
location, replacing only the index entry and its checked lookups. This avoids
silently skipping other computations or their errors. Inline tables have a
stricter limit: their other entries must be constants or simple scalar reads.
Tables exposed elsewhere, dynamic keys, uncertain selectors, or multiple index
uses do not receive a speculative replacement.

## Safety boundary

The advisor moves only single-use index expressions and supported closed,
side-effect-free formatting of them. It does not move arbitrary function calls,
random computations, expressions depending on reassigned inputs, or operations
whose failure or value type could change. It preserves original native Jinja
conditions, including omitted `else` and Boolean short-circuit behavior, rather
than interpreting them using sample episodes.

Each proposed source edit is parsed again and checked against the intended
syntax-tree edit. This is not a proof based on the selected preview example.
With the same index value, a safe conditional rewrite keeps the rendered result;
reconciliation can subsequently change the number because fewer episodes now
participate in that index.

Suggestions reuse conditions already in the template; index names such as
`extra` have no special meaning. Ambiguous scopes, reassignments, or opaque
index-dependent code keep the generic warning rather than guessing intent.
Complex Jinja does not become invalid because advice is unavailable.

Advice may be temporarily unavailable or incomplete while typing. It never adds
validation restrictions to the LMP or changes path rendering, index assignment,
or the save-time reconciliation rules.
