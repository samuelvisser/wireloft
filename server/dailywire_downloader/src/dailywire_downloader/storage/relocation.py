"""Transactional, collision-safe relocation of arbitrary media/auxiliary paths."""
from __future__ import annotations

import errno
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from ..errors import DownloadCancelled
from .copying import copy_file
from .temporary import _publish_complete_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PathMove:
    source: Path
    destination: Path


@dataclass
class _Staged:
    move: PathMove
    staging: Path
    published: bool = False


def _private_path(path: Path) -> Path:
    return path.with_name(f'.{path.name}.wireloft-rename-{uuid4().hex}.tmp')


def _move(source: Path, destination: Path, should_cancel: Callable[[], bool]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if should_cancel():
        raise DownloadCancelled('File relocation canceled')
    try:
        _publish_complete_file(source, destination)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    portable = _private_path(destination)
    try:
        if source.is_dir():
            def copy_one(src, dst):
                copy_file(Path(src), Path(dst), progress=lambda _: None, should_cancel=should_cancel)
                return str(dst)
            shutil.copytree(source, portable, copy_function=copy_one)
        else:
            copy_file(source, portable, progress=lambda _: None, should_cancel=should_cancel)
        _publish_complete_file(portable, destination)
        if source.is_dir():
            shutil.rmtree(source)
        else:
            source.unlink()
    finally:
        if portable.is_dir():
            shutil.rmtree(portable)
        else:
            portable.unlink(missing_ok=True)


class RelocationTransaction:
    """Evacuate all sources before publishing, so cycles do not overwrite files.

    The application must roll back this object if its final database commit
    fails. Rollback itself never overwrites a newly-created external path.
    """
    def __init__(self, moves: tuple[PathMove, ...], should_cancel: Callable[[], bool] = lambda: False):
        self.moves = tuple(move for move in moves if move.source != move.destination)
        self.should_cancel = should_cancel
        self.staged: list[_Staged] = []

    def execute(self, progress: Callable[[int], None] = lambda _: None) -> None:
        sources = {move.source for move in self.moves}
        if len(sources) != len(self.moves) or len({move.destination for move in self.moves}) != len(self.moves):
            raise FileExistsError('Multiple managed artifacts claim the same path')
        for move in self.moves:
            if move.source.is_symlink() or move.destination.is_symlink():
                raise ValueError('Managed artifacts cannot be symbolic links')
            if move.destination.exists() and move.destination not in sources:
                raise FileExistsError(f'Destination already exists: {move.destination}')
        try:
            for index, move in enumerate(self.moves):
                staging = _private_path(move.source)
                _move(move.source, staging, self.should_cancel)
                self.staged.append(_Staged(move, staging))
                progress(int(40 * (index + 1) / len(self.moves)))
            for index, item in enumerate(self.staged):
                _move(item.staging, item.move.destination, self.should_cancel)
                item.published = True
                progress(40 + int(50 * (index + 1) / len(self.staged)))
        except BaseException:
            self.rollback()
            raise

    def rollback(self) -> None:
        # Do not restore cycle sources until every published output is evacuated.
        for item in self.staged:
            if item.published and item.move.destination.exists():
                try:
                    _move(item.move.destination, item.staging, lambda: False)
                    item.published = False
                except OSError:
                    logger.exception('Could not evacuate relocation output %s', item.move.destination)
        for item in reversed(self.staged):
            if item.staging.exists():
                try:
                    _move(item.staging, item.move.source, lambda: False)
                except OSError:
                    logger.exception('Preserving relocation staging file %s for recovery', item.staging)
