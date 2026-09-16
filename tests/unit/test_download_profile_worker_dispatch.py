from task_manager.tasks.media_download_operations import on_media_download_task_terminal
from task_manager.tasks.workers.download_profile_worker import download_profile_worker


def test_download_profile_worker_drains_shared_queue_after_terminal_run():
    """Profile state must not gate execution of work that is already queued."""
    assert download_profile_worker._task_meta.terminal_callback is on_media_download_task_terminal
