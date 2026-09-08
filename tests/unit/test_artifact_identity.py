from __future__ import annotations

import os


def test_artifact_identity_survives_rename(tmp_path):
    from backend.utils.artifact_identity import inspect_artifact

    original = tmp_path / "original.bin"
    renamed = tmp_path / "renamed.bin"
    original.write_bytes(b"artifact contents")

    before = inspect_artifact(original)
    os.rename(original, renamed)
    after = inspect_artifact(renamed)

    assert after.size_bytes == before.size_bytes
    assert after.fingerprint == before.fingerprint


def test_artifact_fingerprint_distinguishes_same_size_content(tmp_path):
    from backend.utils.artifact_identity import inspect_artifact

    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"hello world")
    second.write_bytes(b"HELLO WORLD")

    first_identity = inspect_artifact(first)
    second_identity = inspect_artifact(second)

    assert first_identity.size_bytes == second_identity.size_bytes
    assert first_identity.fingerprint != second_identity.fingerprint


def test_large_artifact_fingerprint_samples_middle_and_end(tmp_path):
    from backend.utils.artifact_identity import inspect_artifact

    sample_size = 64 * 1024
    original = tmp_path / "large.bin"
    changed_middle = tmp_path / "changed-middle.bin"
    changed_end = tmp_path / "changed-end.bin"
    payload = bytearray(b"a" * (sample_size * 4))
    original.write_bytes(payload)

    middle_payload = bytearray(payload)
    middle_payload[len(middle_payload) // 2] = ord("b")
    changed_middle.write_bytes(middle_payload)

    end_payload = bytearray(payload)
    end_payload[-1] = ord("c")
    changed_end.write_bytes(end_payload)

    original_identity = inspect_artifact(original)
    assert inspect_artifact(changed_middle).fingerprint != original_identity.fingerprint
    assert inspect_artifact(changed_end).fingerprint != original_identity.fingerprint
