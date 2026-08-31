"""Migrate Local Media Profile output paths to Jinja.

Revision ID: c91e4a6f72d0
Revises: c4ab8e7d1f20
Create Date: 2026-08-30

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c91e4a6f72d0"
down_revision: Union[str, None] = "c4ab8e7d1f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_PLACEHOLDER = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")
_JINJA_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_MEDIA_TYPE_SUFFIX = "{% if media_type != 'movie' %}-{{ media_type }}{% endif %}"


def upgrade() -> None:
    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT id, type, output_template, append_media_type_to_filename "
        "FROM local_media_profiles"
    )).mappings()

    for profile in profiles:
        output_template = _LEGACY_PLACEHOLDER.sub(
            lambda match: "{{ " + match.group(1) + " }}",
            profile["output_template"],
        )
        if (
            profile["type"] == "movie"
            and profile["append_media_type_to_filename"]
            and output_template.endswith(".ext")
        ):
            output_template = output_template[:-4] + _MEDIA_TYPE_SUFFIX + ".ext"
        connection.execute(
            sa.text(
                "UPDATE local_media_profiles "
                "SET output_template = :output_template, append_media_type_to_filename = 0 "
                "WHERE id = :profile_id"
            ),
            {"output_template": output_template, "profile_id": profile["id"]},
        )
    with op.batch_alter_table("local_media_profiles", schema=None) as batch_op:
        batch_op.alter_column(
            "append_media_type_to_filename",
            existing_type=sa.Boolean(),
            server_default=sa.false(),
            existing_nullable=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT id, output_template FROM local_media_profiles"
    )).mappings()

    for profile in profiles:
        output_template = profile["output_template"]
        had_legacy_suffix = output_template.endswith(_MEDIA_TYPE_SUFFIX + ".ext")
        if had_legacy_suffix:
            output_template = output_template[:-(len(_MEDIA_TYPE_SUFFIX) + 4)] + ".ext"
        output_template = _JINJA_VARIABLE.sub(
            lambda match: "{" + match.group(1) + "}",
            output_template,
        )
        connection.execute(
            sa.text(
                "UPDATE local_media_profiles "
                "SET output_template = :output_template, append_media_type_to_filename = :append_suffix "
                "WHERE id = :profile_id"
            ),
            {
                "output_template": output_template,
                "append_suffix": 1 if had_legacy_suffix else 0,
                "profile_id": profile["id"],
            },
        )
    with op.batch_alter_table("local_media_profiles", schema=None) as batch_op:
        batch_op.alter_column(
            "append_media_type_to_filename",
            existing_type=sa.Boolean(),
            server_default=sa.true(),
            existing_nullable=False,
        )
