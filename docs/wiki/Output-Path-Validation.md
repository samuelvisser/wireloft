# Output path validation

WireLoft checks Local Media Profiles of the same type for output layouts that can conflict. Changing video quality alone does not make a filename different; audio, video and adaptive HLS use different output extensions in the profile check.

## Conditional templates

The check analyzes Jinja rather than rendering a made-up episode. It examines `if`, `elif`, `else` and inline conditional expressions, keeping the conditions attached to each possible output. A conflict limited to auxiliary episodes can therefore be detected even when no auxiliary episodes are currently indexed.

Contradictory conditions are excluded. Two branches do not collide for the same episode merely because their text matches when one requires `episode_type == "aux"` and the other requires `episode_type != "aux"`.

Assignments, aliases, string concatenation, scoped `with` blocks, captured text, ordinary macros and small fixed loops are analyzed. Jinja itself evaluates constant filters and expressions. WireLoft also applies its filename restrictions and known metadata aliases, such as `title` and `episode_title` for shows.

Movies and their extras are considered separately: an extra's `title` is not its parent `movie_title`. Show scope remains a UI availability filter, not a guarantee that profiles cannot manage the same episode.

A detected conflict is reported under **Output path template**, naming the existing Local Media Profile. The same check runs when creating and updating profiles.

## Shared analysis with show artwork

Show artwork uses the same analysis to find a shared show directory. Actual show metadata is known while episode and season values remain variable. Show-specific rules still recognize literal season directories such as `Season 01` and refuse roots without show identity.

## Limits and file safety

The result distinguishes a detected overlap, disjoint output and an inconclusive comparison. Static analysis is not a complete proof about every possible Jinja program, every pair of media items or every filesystem. Arbitrary relationships between filters, data-dependent loops, recursive macros, changed macro closures and large expansions can remain inconclusive. Profile-specific custom indexes are not assumed equal across profiles, and validation never creates or simulates index assignments.

Inconclusive comparisons do not block saving an otherwise valid profile and are not classified as proven safe. Separate directories or explicit format/quality suffixes remain the clearest way to separate intended outputs. Existing filesystem collision protections during downloads and renames remain authoritative, including when different media items happen to have the same title.
