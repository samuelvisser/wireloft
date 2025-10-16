# WireLoft Controller

### Purpose
- Provides the background task “controller” layer for WireLoft.
- Central place to define and register task definitions that are executed by the scheduler.
- Simple registry API to declare capabilities like default max retries and whether a task tracks progress.

### What’s included
- A thin registry wrapper: wireloft_controller.registry.task
- A sample task: download_series_thumbnail
  - definition key: download_series_thumbnail
  - allowed resource types: ["download_profile_series"]
  - capabilities: default_max_retries=5, tracks_progress=False
  - behavior: When triggered with a DownloadProfileSeries id, downloads the series thumbnail into the media profile’s output directory (derived from output_template).

### Install/enable
- This package is part of the workspace (server/*). No separate install is required in dev.
- The backend app imports wireloft_controller on startup so that task definitions are registered before syncing to the DB.

### CLI
- A small CLI is available to list and run controller workers directly.
- After installing/in workspace, use:
  - List tasks: `controller list` (add `--verbose` for details)
  - Run a task by key: `controller run --key <definition_key> [--resource-id <id>] [--show-slug <slug>] [--arg name=value --arg other=123]`
- Example:
  - `controller run --key index_show_worker --show-slug the-ben-shapiro-show`

### Defining a new task
- Create a new module under wireloft_controller/tasks and decorate a function:

  from wireloft_controller.registry import task

  @task(
      key="my_task",
      title="My Task",
      description="What it does",
      allowed_resource_types=("show",),
      default_max_retries=3,
      tracks_progress=True,
  )
  async def my_task(*, resource_id: int, progress):
      # Do work; use `progress.set(percent, message)` if tracks_progress=True
      ...

### Capabilities
- default_max_retries: default retry policy if not overridden by schedule or API trigger.
- tracks_progress: metadata flag signaling whether the task reports intermediate progress.

### Trigger via API
- Endpoint: POST /api/tasks/runs/trigger
- Query parameters:
  - definition_key: string (e.g., download_series_thumbnail)
  - resource_type: string (e.g., download_profile_series)
  - resource_id: integer (the ID of the DownloadProfileSeries)
  - max_retries: integer (optional override)

### Example curl

  curl -X POST "http://localhost:8000/api/tasks/runs/trigger?definition_key=download_series_thumbnail&resource_type=download_profile_series&resource_id=123&max_retries=5" \
       -H "Authorization: Bearer <token>"

### Programmatic trigger (library use)

  from wireloft_scheduler.executor import trigger_now
  job_id = trigger_now(
      def_key="download_series_thumbnail",
      resource_type="download_profile_series",
      resource_id=123,
      max_retries=5,
  )

### Notes
- The backend app syncs all registered tasks to the TaskDefinition table on startup (if the scheduler is enabled in settings). Ensure your task module is importable at startup.
- The sample task saves the file as series_thumbnail.jpg/png under the media profile’s output directory (parent of output_template). If the show has no thumbnail URL, the task will fail (and be retried according to policy).