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

## Migrations
WireLoft knows about two separate migration paths, each to serve a separate need:
- Database migrations
- Background migrations

Database migrations should be used strictly to change the database schema. It can move local data
around if needed, but it can never use external resources such as API calls or the filesystem.
Database migrations are expected to finish relatively quickly due to their local- only nature.
They run before WireLoft starts anything else.

Background migrations run in the background while WireLoft is running. They can use external resources
such as API calls or the filesystem if needed. They are designed specifically for migrations that are
expected to take longer and therefore do not interrupt the WireLoft startup process.
Background migrations do, however, pause all scheduled work while they are running.

### Database migrations
If you need to do any database migrations to implement a feature, please follow these guidelines:
- Create a new alembic migration script in server/backend/src/backend/db/alembic/versions/
- Run `backend-api db history` to verify the new migration is the current head, and no multiple
migration heads exist.

### Background migrations
If you need to do any API/ filesystem or any other long- running migration work to implement a feature
or fix faulty data caused by a historical bug, please follow these guidelines:
- Create a new background migration script in server/backend/src/backend/db/background_migrations/versions/.
- Name it `<revision>_<description>.py`, using an opaque 12-character lowercase hexadecimal revision
  like Alembic. The description belongs only in the filename suffix/title; never encode migration
  semantics in the revision itself.
- Declare `revision` and `down_revision` in the migration module, just like Alembic.
- When consolidating prerelease background migrations for a release, keep the revision of the latest
  migration being replaced so development/test databases that already reached it remain current.
- Run `backend-api background-migrations history` to verify the new migration is the current head, and no multiple
migration heads exist.

### Legacy stored values
WireLoft is still in an early stage and application code should not contain compatibility handling
for legacy persisted values. If a change renames or otherwise changes the representation of a stored
configuration value, key, enum/string value, profile option, or other persisted database value, add
a data migration that rewrites existing stored data to the new canonical representation.

After that migration, frontend and backend application code must only know about the current canonical
values. Do not add aliases, legacy-value normalization, fallback branches, dual-read/dual-write logic,
or other runtime handling whose only purpose is to support values used by an older WireLoft version.
Legacy identifiers may appear in the migration file itself and in migration-specific tests or
fixtures needed to verify that migration, but not in normal application code. Treat legacy data
compatibility as a one-time migration concern rather than a permanent application-code concern.

### Migration squashing
When releasing a new version of WireLoft, I will often ask you to merge all migrations after the last
migration in the previous official release into one, making it one big migration from the previous
WireLoft version into the next. When I ask you to do this, please make sure the new merged migration 
file uses the same version number as the last pre-merge migration did. In this way, my testing 
environments that have been upgrading through these smaller upgrades, will know they are already 
up-to-date and do not require an update even if the migration file merged everything together.

I often like to merge Alembic migrations for updates, but keep background migrations separate. Though
I might change how I do this for any particular release, if I ask you to prepare for a new release
and did not ask you to merge migrations, please always ask me whether I want that. I might just simply
have forgotten to ask you.

## API model boundaries
WireLoft uses Pydantic as the API mapping and serialization boundary. Keep that boundary declarative:
- Prefer `model_validate()`, `from_attributes`, field aliases/`AliasPath`, discriminated unions, and small typed
  source envelopes over manually building dictionaries that mirror response models.
- Services should compute business facts and select data sources, but must not manually serialize enums/datetimes,
  duplicate response defaults, or validate -> dump -> rebuild another response model.
- Do not move a hand-written serializer into a Pydantic validator. Validators should express actual validation or
  small semantic derivations; straightforward source mapping belongs in Pydantic field aliases.
- Task manager and other lower-level packages must not import `backend.api.models`, `backend.api.endpoints`, or
  other API-layer modules. Shared application/domain behavior belongs below `backend.api` so both workers and
  endpoints can call it.
- API request models describe HTTP input. Do not reuse them as internal domain DTOs for Daily Wire records or worker
  data merely because the fields currently happen to overlap.

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

## Tests
You are allowed to create tests for your work. However, make sure to never add domain — level wiring
just to support tests. You can add test helpers, but those belong in the test files themselves.

Never add helpers or other domain-level functions just to support tests. Only use domain helpers
when they are necessary for the domain logic itself.

### Test your work
Before you push your branch, please run all appropriate tests to verify your work.  
Also be sure to launch both the backend and frontend servers and verify your work in the UI.
First, run `uv sync` and `npm install` from the repository root to install all dependencies.
The backend is started with: `backend-api run` and the frontend is started with `npm run dev` from the repository root.
If your environment is not able to run any of these tests, you can skip this step.

## Font Awesome pro and free icon versions
WireLoft uses a paid Font Awesome kit for its full icon set, but access to that kit is not required for normal development, automated agents, CI, or public contributors.

Do not replace or remove an intended Pro icon merely because the paid kit is unavailable in your environment. Normal dev builds deliberately use the centralized registry in `ui/src/icons/fontAwesome.ts` and the mappings in `ui/src/icons/freeIconFallbacks.json`.

When adding an icon that is Pro-only, add a visually and semantically similar Font Awesome Free icon to `freeIconFallbacks.json`. Both icon build commands run a validator that rejects a referenced Pro-only icon when no Free fallback is defined.
