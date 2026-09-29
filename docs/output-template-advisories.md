# Custom Index advice in the template editor

WireLoft uses normal Jinja execution for output templates. The editor can now
explain likely mistakes without changing the template's meaning or preventing
an otherwise valid Local Media Profile from being saved.

Each referenced Custom Index has its own warning when appropriate:

- An undefined Indexing Value renders as empty. Add the definition in the current
  form or remove the reference. This remains a warning, not a save error.
- An index that is guaranteed to run for every episode receives an all-episode
  warning. This is intentional for some sequences. For an extras-only sequence,
  put the index call inside the condition that identifies an extra.

The advice uses the template and definitions currently in the form, including
unsaved edits. It does not inspect the selected example or scan the episode
library. Preview requests continue independently and never wait for advice.

## Suggested code changes

When an unconditional index declaration flows through a single-use chain of
variables or formatting into an existing conditional string assignment, the
editor can suggest a native Jinja set block. For example:

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

Expand **Suggested change** to review the original assignments and replacement,
then choose **Use suggested change** to update the form. Nothing is applied or
saved automatically. Review the preview before saving: restricting membership
can renumber the participating episodes when Custom Indexes are reconciled.

Suggestions reuse conditions already in the template; index names such as
`extra` have no special meaning. Multiple uses, ambiguous scopes, uncertain value
types or operations that cannot safely be moved can prevent a suggestion. The
all-episode warning still remains when that fact is known. Complex Jinja does
not become invalid merely because the advisory cannot offer a rewrite.

Advice may be temporarily unavailable or incomplete while typing. It never adds
validation restrictions to the LMP or changes path rendering, index assignment,
or the save-time reconciliation rules.
