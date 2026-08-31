"""Standardize parent-movie and current-item template variables.

Revision ID: e5b7c9d1f3a2
Revises: c91e4a6f72d0
Create Date: 2026-08-31

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from jinja2 import Environment


revision: str = "e5b7c9d1f3a2"
down_revision: Union[str, None] = "c91e4a6f72d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DATE_FIELDS = (
    "date",
    "time",
    "datetime",
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "second",
)
_UPGRADE_VARIABLES = {
    "movie": "movie_slug",
    **{field: f"movie_{field}" for field in _DATE_FIELDS},
}
_DOWNGRADE_VARIABLES = {
    f"movie_{field}": field for field in _DATE_FIELDS
}


def _rewrite_jinja_names(template: str, replacements: dict[str, str]) -> str:
    """Rewrite variable-name tokens without changing strings or plain path text."""
    environment = Environment()
    return "".join(
        replacements.get(value, value) if token_type == "name" else value
        for _line, token_type, value in environment.lex(template)
    )


def _rewrite_movie_profiles(replacements: dict[str, str]) -> None:
    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT id, output_template FROM local_media_profiles WHERE type = 'movie'"
    )).mappings()
    for profile in profiles:
        output_template = _rewrite_jinja_names(
            profile["output_template"],
            replacements,
        )
        connection.execute(
            sa.text(
                "UPDATE local_media_profiles SET output_template = :output_template "
                "WHERE id = :profile_id"
            ),
            {"output_template": output_template, "profile_id": profile["id"]},
        )


def upgrade() -> None:
    with op.batch_alter_table("movie_extras", schema=None) as batch_op:
        batch_op.add_column(sa.Column("published_date", sa.DateTime(), nullable=True))
    _rewrite_movie_profiles(_UPGRADE_VARIABLES)


def downgrade() -> None:
    _rewrite_movie_profiles(_DOWNGRADE_VARIABLES)
    with op.batch_alter_table("movie_extras", schema=None) as batch_op:
        batch_op.drop_column("published_date")
