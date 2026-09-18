# AI agent and contributor guidance

## Git usage
When I ask you to implement a new feature, please follow these guidelines:
- Create a new branch from develop. If your are an OpenAI product create it inside
codex/, if you are a Anthropic product, place it inside claude/. If you are anything
else, use a relevant name to identify yourself within git.
- If I ask you to do follow-up work on that same feature, please continue to use the
same branch. Only base a new branch on develop again if you are implementing a new feature.
- When you are done, please squash your commits into a single commit and push to your branch.
- Only squash within a single request. After you are done with a commit, I add context or ask 
for another change, this should be its own new commit.

### OpenAI GitHub connector
If you are an OpenAI product, it is important to know the GitHub connector you use often stalls
for long sessions. It just stops responding, causing your work to stall as well.
To work around this, I found it is often better to create and push small commits through the connector 
while you are working, and only when done at the end squash all commits into a single commit.  

If the GitHub connector still stalls, please try to sleep for a little and then try again instead
of stalling the entire session.

## Database migrations
If you need to do any database migrations to implement the feature, please follow these guidelines:
- Create a new alembic migration script in server/backend/src/backend/db/alembic/versions/
- Run `backend db history` to verify the new migration is the current head, and no multiple
migration heads exist.

### Legacy stored values
WireLoft is still in an early stage and application code should not contain compatibility handling
for legacy persisted values. If a change renames or otherwise changes the representation of a stored
configuration value, key, enum/string value, profile option, or other persisted database value, add
an Alembic data migration that rewrites existing stored data to the new canonical representation.

After that migration, frontend and backend application code must only know about the current canonical
values. Do not add aliases, legacy-value normalization, fallback branches, dual-read/dual-write logic,
or other runtime handling whose only purpose is to support values used by an older WireLoft version.
Legacy identifiers may appear in the Alembic migration itself and in migration-specific tests or
fixtures needed to verify that migration, but not in normal application code. Treat legacy data
compatibility as a one-time migration concern rather than a permanent application-code concern.

## Forms
WireLoft forms are configured within React Hook Form and Zod to ensure field validation in the frontend.
However, all backend API endpoints use Pydantic models to do their own validation. In most cases,
validation should always happen in both the frontend (user-friendly) and the backend for security.

To handle backend validation errors gracefully, WireLoft provides a ServerAwareSubmit helper that
makes sure backend validation errors still end up showing under fields that caused them, including a
fallback field as a 'catch all'. This goes not only for Pydantic validation errors, but also errors
thrown by the SQLAlchemy database layer. It even tries to map database field errors to the correct
RHF form fields.

Form default values, unless defined dynamically, should be defined through Zod defaults. Those should
then be picked up by React Hook Form and used as actual default values. Only deviate from this if the
default changes dynamically based on certain conditions.

Make sure to use this structure for any form adjustments and especially any new forms.

## Wiki
When making big changes, you are allowed to update the WireLoft Wiki, too. 
However, keep in mind that the Wiki’s goal is user-facing: it should tell users things 
they might want to know for using WireLoft as a product. 
The wiki is not for documenting exact development implementations. 
It should also be easy to understand for a moderately tech-literate audience.

The wiki should document the big picture for WireLoft: code comments are for explaining 
programming implementation details.

## The Daily Wire
When referring to The Daily Wire, in most cases, use the full name, "The Daily Wire". 
However, in some contexts, it may read better to use "Daily Wire" instead. This is not the 'correct'
name though, so should only be used if "The Daily Wire" reads awkwardly in the sentence.

## Test your work
Before you push your branch, please run all appropriate tests to verify your work.  
Also be sure to launch both the backend and frontend servers and verify your work in the UI.
First, run `uv sync` and `npm install` from the repository root to install all dependencies.
The backend is started with: `backend-api run` and the frontend is started with `npm run dev` from the repository root.
If your environment is not able to run any of these tests, you can skip this step.

### Frontend icon builds
WireLoft uses a paid Font Awesome kit for its full icon set, but access to that kit is never required for normal development, automated agents, CI, or public contributors.

For a clean checkout without Font Awesome credentials, install UI dependencies with `npm --prefix ui ci --registry=https://registry.npmjs.org`. The paid kit is an optional dependency; npm can skip it when credentials are unavailable while still installing other optional dependencies required by the frontend toolchain.

From the repository root:

- `npm run build` uses Font Awesome Free and is the normal validation path.
- `npm run build:pro-icons` uses the paid Font Awesome kit and requires valid Font Awesome npm credentials plus access to the WireLoft kit.

Free Font Awesome packages are pinned to the same Font Awesome 6 generation as the paid WireLoft kit so icons that exist in both sets render consistently.

Do not replace or remove an intended Pro icon merely because the paid kit is unavailable in your environment. Free builds deliberately use the centralized registry in `ui/src/icons/fontAwesome.ts` and the mappings in `ui/src/icons/freeIconFallbacks.json`.

When adding an icon that is Pro-only, add a visually and semantically similar Font Awesome Free icon to `freeIconFallbacks.json`. Both icon build commands run a validator that rejects a referenced Pro-only solid icon when no Free fallback is defined.

A successful normal `npm run build` is sufficient frontend build validation for agents and contributors that do not have the paid kit.
