from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class MediaServerMetadata:
    kind: str
    title: str
    description: str | None = None
    unique_id: str | None = None
    source_url: str | None = None
    show_title: str | None = None
    season_number: int | None = None
    episode_index: int | None = None
    episode_number: int | None = None
    aired: date | None = None
    release_date: date | None = None
    duration_seconds: float | None = None
    authors: tuple[str, ...] = field(default_factory=tuple)
    genres: tuple[str, ...] = field(default_factory=tuple)
    directors: tuple[str, ...] = field(default_factory=tuple)
    writers: tuple[str, ...] = field(default_factory=tuple)
    cast: tuple[str, ...] = field(default_factory=tuple)
    studios: tuple[str, ...] = field(default_factory=tuple)
    language: str | None = None
    country: str | None = None
    content_rating: str | None = None
    parent_movie_title: str | None = None
    media_type: str | None = None

    def ffmpeg_tags(self) -> dict[str, str]:
        tags: dict[str, str] = {"title": self.title}
        if self.description:
            tags["description"] = self.description
            tags["comment"] = self.description
        if self.show_title:
            tags["show"] = self.show_title
            tags["album"] = self.show_title
        if self.authors:
            joined = ", ".join(self.authors)
            tags["artist"] = joined
            tags["album_artist"] = joined
        if self.aired:
            tags["date"] = self.aired.isoformat()
        elif self.release_date:
            tags["date"] = self.release_date.isoformat()
        if self.season_number is not None:
            tags["season_number"] = str(self.season_number)
        if self.episode_number is not None:
            tags["episode_id"] = str(self.episode_number)
        if self.episode_index is not None:
            tags["episode_sort"] = str(self.episode_index)
        if self.genres:
            tags["genre"] = ", ".join(self.genres)
        if self.directors:
            tags["director"] = ", ".join(self.directors)
        if self.writers:
            tags["writer"] = ", ".join(self.writers)
        if self.cast:
            tags["actor"] = ", ".join(self.cast)
        if self.studios:
            tags["publisher"] = ", ".join(self.studios)
        if self.language:
            tags["language"] = self.language
        if self.country:
            tags["country"] = self.country
        if self.content_rating:
            tags["rating"] = self.content_rating
        if self.source_url:
            tags["purl"] = self.source_url
        if self.unique_id:
            tags["dailywire_id"] = self.unique_id
        if self.media_type:
            tags["media_type"] = self.media_type
        return tags


def write_nfo(media_path: str, metadata: MediaServerMetadata) -> str:
    destination = Path(media_path).with_suffix(".nfo")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part_path = Path(str(destination) + ".part")
    placeholder_fd: int | None = None
    placeholder_created = False
    try:
        placeholder_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o666,
        )
        placeholder_created = True
        os.close(placeholder_fd)
        placeholder_fd = None
        ET.ElementTree(_nfo_root(metadata)).write(
            part_path,
            encoding="utf-8",
            xml_declaration=True,
        )
        os.replace(part_path, destination)
        return str(destination)
    except BaseException:
        if placeholder_fd is not None:
            os.close(placeholder_fd)
        part_path.unlink(missing_ok=True)
        if placeholder_created:
            destination.unlink(missing_ok=True)
        raise


def _nfo_root(metadata: MediaServerMetadata) -> ET.Element:
    root = ET.Element("episodedetails" if metadata.kind == "episode" else "movie")
    _text(root, "title", metadata.title)
    _text(root, "plot", metadata.description)
    if metadata.unique_id:
        unique = ET.SubElement(root, "uniqueid", {"type": "dailywire", "default": "true"})
        unique.text = metadata.unique_id
    _text(root, "showtitle", metadata.show_title)
    _text(root, "season", metadata.season_number)
    _text(root, "episode", metadata.episode_number)
    _text(root, "aired", metadata.aired)
    _text(root, "premiered", metadata.release_date)
    if metadata.release_date:
        _text(root, "year", metadata.release_date.year)
    if metadata.duration_seconds and metadata.duration_seconds > 0:
        _text(root, "runtime", max(1, round(metadata.duration_seconds / 60)))
    _text(root, "mpaa", metadata.content_rating)
    _text(root, "country", metadata.country)
    _text(root, "language", metadata.language)
    _text(root, "parenttitle", metadata.parent_movie_title)
    _text(root, "mediatype", metadata.media_type)
    _text(root, "source", metadata.source_url)

    for value in metadata.genres:
        _text(root, "genre", value)
    for value in metadata.directors:
        _text(root, "director", value)
    for value in metadata.writers:
        _text(root, "credits", value)
    for value in metadata.studios:
        _text(root, "studio", value)
    for value in metadata.authors:
        _text(root, "credits", value)
    for value in metadata.cast:
        actor = ET.SubElement(root, "actor")
        _text(actor, "name", value)
    return root


def _text(parent: ET.Element, name: str, value) -> None:
    if value is None or value == "":
        return
    element = ET.SubElement(parent, name)
    element.text = str(value)


def render_nfo(metadata: MediaServerMetadata) -> bytes:
    """Generate the exact sidecar payload before filesystem work is planned."""
    return ET.tostring(_nfo_root(metadata), encoding="utf-8", xml_declaration=True)
