from __future__ import annotations

import threading


def test_process_shared_capacity_limiter_blocks_independent_instances(tmp_path):
    from dailywire_downloader.capacity import ProcessSharedCapacityLimiter

    lock_root = tmp_path / "download-capacity"
    first = ProcessSharedCapacityLimiter(1)
    second = ProcessSharedCapacityLimiter(1)
    first.configure(1, lock_root=lock_root)
    second.configure(1, lock_root=lock_root)

    first_entered = threading.Event()
    release_first = threading.Event()
    second_waiting = threading.Event()
    second_entered = threading.Event()
    errors: list[BaseException] = []

    def first_worker():
        try:
            with first.acquire(
                should_cancel=lambda: False,
                waiting=lambda _waiting: None,
            ):
                first_entered.set()
                assert release_first.wait(2)
        except BaseException as exc:
            errors.append(exc)

    def second_worker():
        try:
            assert first_entered.wait(2)

            def waiting(is_waiting: bool) -> None:
                if is_waiting:
                    second_waiting.set()

            with second.acquire(
                should_cancel=lambda: False,
                waiting=waiting,
            ):
                second_entered.set()
        except BaseException as exc:
            errors.append(exc)

    first_thread = threading.Thread(target=first_worker)
    second_thread = threading.Thread(target=second_worker)
    first_thread.start()
    second_thread.start()

    assert first_entered.wait(2)
    assert second_waiting.wait(2)
    assert not second_entered.wait(0.1)

    release_first.set()
    assert second_entered.wait(2)

    first_thread.join(2)
    second_thread.join(2)
    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert errors == []


def test_process_shared_capacity_limiter_honors_configured_slot_count(tmp_path):
    from dailywire_downloader.capacity import ProcessSharedCapacityLimiter

    lock_root = tmp_path / "download-capacity"
    limiters = [ProcessSharedCapacityLimiter(2) for _ in range(3)]
    for limiter in limiters:
        limiter.configure(2, lock_root=lock_root)

    release = threading.Event()
    entered = [threading.Event() for _ in limiters]
    waiting = [threading.Event() for _ in limiters]
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            with limiters[index].acquire(
                should_cancel=lambda: False,
                waiting=lambda value, index=index: waiting[index].set() if value else None,
            ):
                entered[index].set()
                assert release.wait(2)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(index,))
        for index in range(len(limiters))
    ]
    threads[0].start()
    threads[1].start()
    assert entered[0].wait(2)
    assert entered[1].wait(2)

    threads[2].start()
    assert waiting[2].wait(2)
    assert not entered[2].wait(0.1)

    release.set()
    assert entered[2].wait(2)

    for thread in threads:
        thread.join(2)
        assert not thread.is_alive()
    assert errors == []
