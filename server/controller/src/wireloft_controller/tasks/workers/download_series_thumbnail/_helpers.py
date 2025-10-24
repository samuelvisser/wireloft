from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def ensure_dir_from_template(output_template: str) -> Path:
    # The output_template ends with something like ".../file.ext"; take its directory
    p = Path(output_template)

    # If template contains placeholders, directory still resolves correctly
    dir_path = p.parent
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


def pick_thumbnail_url(show) -> Optional[str]:
    # Try in preference order
    for attr in ("thumbnail_landscape_path", "thumbnail_portrait_path", "thumbnail_square_path"):
        val = getattr(show, attr, None)
        if val:
            return val
    return None



