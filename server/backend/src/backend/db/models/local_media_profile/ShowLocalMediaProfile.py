from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.db.mixins.HasMetadataMixin import HasMetadataMixin

from backend.types.local_media_profile_types import LocalMediaProfileType, ShowLocalMediaProfileScope

from .LocalMediaProfileBase import LocalMediaProfileBase


class ShowLocalMediaProfile(LocalMediaProfileBase, HasMetadataMixin):
    __tablename__ = "local_media_profiles_show"
    __metadata_parent_table__ = "local_media_profiles"
    __mapper_args__ = {"polymorphic_identity": LocalMediaProfileType.SHOW.value}

    id: Mapped[int] = mapped_column(
        ForeignKey("local_media_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    show_scope: Mapped[str] = mapped_column(
        default=ShowLocalMediaProfileScope.BOTH.value,
        server_default=ShowLocalMediaProfileScope.BOTH.value,
        nullable=False,
    )

    @property
    def indexing_values(self):
        from backend.utils.custom_index import get_indexing_value_definitions
        return get_indexing_value_definitions(self)
