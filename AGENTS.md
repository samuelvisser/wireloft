# AI agent and contributor guidance

## Frontend icon builds

WireLoft uses a paid Font Awesome kit for its full icon set, but access to that kit is never required for normal development, automated agents, CI, or public contributors.

For a clean checkout without Font Awesome credentials, install UI dependencies with `npm --prefix ui install --omit=optional --package-lock=false --registry=https://registry.npmjs.org`. The paid kit is an optional dependency, and this explicit public-registry path avoids historical private-registry URLs in the existing lockfile.

From the repository root:

- `npm run build` uses Font Awesome Free and is the normal validation path.
- `npm run build:pro-icons` uses the paid Font Awesome kit and requires valid Font Awesome npm credentials plus access to the WireLoft kit.

Do not replace or remove an intended Pro icon merely because the paid kit is unavailable in your environment. Free builds deliberately use the centralized registry in `ui/src/icons/fontAwesome.ts` and the mappings in `ui/src/icons/freeIconFallbacks.json`.

When adding an icon that is Pro-only, add a visually and semantically similar Font Awesome Free icon to `freeIconFallbacks.json`. Both icon build commands run a validator that rejects a referenced Pro-only solid icon when no Free fallback is defined.

A successful normal `npm run build` is sufficient frontend build validation for agents and contributors that do not have the paid kit.
