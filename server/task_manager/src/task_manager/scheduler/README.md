# Scheduler

WireLoft's scheduler is the execution layer for background work. Task definitions are registered in code, APScheduler decides when a job should run, and durable scheduler tables record what is happening and what happened during execution.

The core boundary is simple:

- `TaskRun` / `TaskOperation` own changing execution state: queued/running state, progress, retries, cancellation, worker errors and execution timing.
- Domain models own library state: shows, episodes, movies, download artifacts and other facts that remain useful after the task is over.

Do not mirror task lifecycle fields onto domain rows. If the UI needs to present a domain object as "downloading" or show a percentage, combine the domain object with its active TaskOperation in the presentation layer.

See [OPERATIONS.md](./OPERATIONS.md) for TaskOperation correlation, progress, cancellation, recovery, constrained queues and frontend polling conventions.
