
def update_progress(progress, percentage: int, msg: str):
    """Small helper to update the progress in any worker"""
    if progress:
        progress.set(percentage, msg)
    print(f"{percentage}%: {msg}")