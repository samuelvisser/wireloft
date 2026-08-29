"""Split local media profiles by media type

Revision ID: 828421f64d03
Revises: 0001
Create Date: 2026-08-29 13:46:07.157304

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '828421f64d03'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _raise_for_duplicate_legacy_profile_settings() -> None:
    duplicate = op.get_bind().execute(sa.text(
        "SELECT output_template, preferred_format, COUNT(*) AS profile_count "
        "FROM local_media_profiles "
        "GROUP BY output_template, preferred_format "
        "HAVING COUNT(*) > 1 "
        "LIMIT 1"
    )).mappings().first()
    if duplicate is not None:
        raise RuntimeError(
            "Local Media Profiles must be unique by type, output template, and "
            "preferred format before this migration can continue; found "
            f"{duplicate['profile_count']} duplicate Show profiles using output "
            f"template '{duplicate['output_template']}' and preferred format "
            f"'{duplicate['preferred_format']}'."
        )


def upgrade() -> None:
    # Legacy profiles are all migrated to the Show type. Check before any DDL
    # so a uniqueness failure leaves the database cleanly at revision 0001.
    _raise_for_duplicate_legacy_profile_settings()

    op.create_table(
        'local_media_profiles_movie',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['id'],
            ['local_media_profiles.id'],
            name=op.f('fk_local_media_profiles_movie_id_local_media_profiles'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_local_media_profiles_movie')),
    )
    op.create_table(
        'local_media_profiles_show',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['id'],
            ['local_media_profiles.id'],
            name=op.f('fk_local_media_profiles_show_id_local_media_profiles'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_local_media_profiles_show')),
    )

    with op.batch_alter_table('local_media_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('type', sa.String(), server_default='show', nullable=False))

    # All profiles created before this discriminator existed were used for
    # show episodes. Joined-table inheritance requires a matching subtype row.
    op.execute(sa.text(
        "INSERT INTO local_media_profiles_show (id) "
        "SELECT id FROM local_media_profiles WHERE type = 'show'"
    ))

    with op.batch_alter_table('local_media_profiles', schema=None) as batch_op:
        batch_op.create_index(
            'uq_local_media_profiles_type_output_template_preferred_format',
            ['type', 'output_template', 'preferred_format'],
            unique=True,
        )

    with op.batch_alter_table('movies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('extended_title', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_table('local_media_profiles_show')
    op.drop_table('local_media_profiles_movie')

    with op.batch_alter_table('movies', schema=None) as batch_op:
        batch_op.drop_column('extended_title')

    with op.batch_alter_table('local_media_profiles', schema=None) as batch_op:
        batch_op.drop_index('uq_local_media_profiles_type_output_template_preferred_format')
        batch_op.drop_column('type')
