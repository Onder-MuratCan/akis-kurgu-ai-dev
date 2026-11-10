"""Frame-based, non-destructive timeline primitives.

All positions are integer frames. Source paths are references; edits never modify media.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from uuid import uuid4

# Limits for documents loaded from disk. Project files can come from other people,
# so every value is type- and range-checked before it reaches FFmpeg filter graphs.
MAX_FRAME = 10 ** 8          # ~38 days at 30 fps
MAX_TRACKS = 64
MAX_CLIPS_PER_TRACK = 10_000
MAX_MARKERS = 10_000
MAX_TEXT = 5_000
MAX_PATH = 4_096
MAX_ID = 128
TRACK_KINDS = {"video", "audio", "text", "overlay"}
CLIP_KEYS = {"source", "start", "length", "source_in", "source_length", "id", "text", "volume", "keyframes"}


def _int(value, name, low=0, high=MAX_FRAME):
    """Accept JSON integers (or integral floats such as 30.0); reject bools, strings and NaN."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be an integer")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{name} must be an integer")
        value = int(value)
    if not low <= value <= high:
        raise ValueError(f"{name} is out of range")
    return value


def _str(value, name, limit, allow_empty=True):
    if not isinstance(value, str) or len(value) > limit or "\0" in value or (not allow_empty and not value):
        raise ValueError(f"{name} must be text up to {limit} characters")
    return value


def _clip_from_dict(data):
    if not isinstance(data, dict) or not set(data) <= CLIP_KEYS:
        raise ValueError("Invalid clip")
    volume = data.get("volume", 1.0)
    if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not math.isfinite(volume):
        raise ValueError("Clip volume must be a number")
    keyframes = data.get("keyframes", {})
    if not isinstance(keyframes, dict) or any(
            not isinstance(name, str) or not isinstance(points, list)
            or any(not isinstance(p, dict) for p in points) for name, points in keyframes.items()):
        raise ValueError("Invalid clip keyframes")
    for points in keyframes.values():
        for point in points:
            point["frame"] = _int(point.get("frame"), "Keyframe frame")
    source_length = data.get("source_length")
    values = {
        "source": _str(data.get("source", ""), "Clip source", MAX_PATH),
        "start": _int(data.get("start"), "Clip start"),
        "length": _int(data.get("length"), "Clip length", 1),
        "source_in": _int(data.get("source_in", 0), "Clip source_in"),
        "source_length": None if source_length is None else _int(source_length, "Clip source_length", 1),
        "text": _str(data.get("text", ""), "Clip text", MAX_TEXT),
        "volume": float(volume),
        "keyframes": keyframes,
    }
    if "id" in data:
        values["id"] = _str(data["id"], "Clip id", MAX_ID, allow_empty=False)
    return Clip(**values)


def _track_from_dict(data):
    if not isinstance(data, dict) or data.get("kind") not in TRACK_KINDS:
        raise ValueError("Invalid track")
    clips = data.get("clips", [])
    muted = data.get("muted", False)
    if not isinstance(clips, list) or len(clips) > MAX_CLIPS_PER_TRACK or not isinstance(muted, bool):
        raise ValueError("Invalid track")
    return Track(kind=data["kind"], name=_str(data.get("name", ""), "Track name", 200),
                 muted=muted, clips=[_clip_from_dict(c) for c in clips])


@dataclass
class Clip:
    source: str
    start: int
    length: int
    source_in: int = 0
    source_length: int | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    text: str = ""
    volume: float = 1.0
    keyframes: dict[str, list[dict]] = field(default_factory=dict)

    def __post_init__(self):
        if not 0 <= self.volume <= 1:
            raise ValueError("Volume must be between 0 and 1")
        if self.start < 0 or self.source_in < 0 or self.length < 1:
            raise ValueError("Invalid clip range")
        if self.source_length is not None and self.source_in + self.length > self.source_length:
            raise ValueError("Clip exceeds source duration")

    @property
    def end(self):
        return self.start + self.length


@dataclass
class Track:
    kind: str
    name: str
    clips: list[Clip] = field(default_factory=list)
    muted: bool = False

    def __post_init__(self):
        if self.kind not in {"video", "audio", "text", "overlay"}:
            raise ValueError("Invalid track type")
        self.validate()

    def validate(self):
        clips = sorted(self.clips, key=lambda c: c.start)
        if any(c.start < 0 or c.source_in < 0 or c.length < 1 or
               (c.source_length is not None and c.source_in + c.length > c.source_length) for c in clips):
            raise ValueError("Invalid clip range")
        if len({c.id for c in clips}) != len(clips):
            raise ValueError("Duplicate clip id")
        if any(a.end > b.start for a, b in zip(clips, clips[1:])):
            raise ValueError("Clips on the same track overlap")

    def add(self, clip: Clip):
        self.clips.append(clip)
        try:
            self.validate()
        except Exception:
            self.clips.remove(clip)
            raise

    def split(self, clip_id: str, frame: int):
        clip = self.find(clip_id)
        offset = frame - clip.start
        if not 0 < offset < clip.length:
            raise ValueError("Split must be inside clip")
        right = Clip(source=clip.source, start=frame, length=clip.length-offset,
                     source_in=clip.source_in+offset, source_length=clip.source_length,
                     text=clip.text, volume=clip.volume)
        for name, points in clip.keyframes.items():
            right.keyframes[name] = [dict(p, frame=p['frame']-offset) for p in points if p['frame'] >= offset]
            clip.keyframes[name] = [p for p in points if p['frame'] < offset]
        clip.length = offset
        self.add(right)
        return right

    def find(self, clip_id: str):
        return next(c for c in self.clips if c.id == clip_id)

    def slip(self, clip_id: str, delta: int):
        clip = self.find(clip_id)
        new_in = clip.source_in + delta
        if new_in < 0 or (clip.source_length is not None and new_in + clip.length > clip.source_length):
            raise ValueError("Slip exceeds source duration")
        clip.source_in = new_in

    def move(self, clip_id: str, start: int):
        clip = self.find(clip_id)
        old = clip.start
        clip.start = start
        try:
            self.validate()
        except ValueError:
            clip.start = old
            raise

    def ripple_delete(self, clip_id: str):
        clip = self.find(clip_id)
        end, length = clip.end, clip.length
        self.clips.remove(clip)
        for other in self.clips:
            if other.start >= end:
                other.start -= length

    def trim_end(self, clip_id: str, end: int, ripple: bool = False):
        clip = self.find(clip_id)
        length = end - clip.start
        if length < 1 or (clip.source_length is not None and clip.source_in + length > clip.source_length):
            raise ValueError("Invalid trim")
        old_length = clip.length
        following = [c for c in self.clips if c.id != clip.id and c.start >= clip.end]
        clip.length = length
        if ripple:
            for other in following:
                other.start += length - old_length
        try:
            self.validate()
        except Exception:
            clip.length = old_length
            if ripple:
                for other in following:
                    other.start -= length - old_length
            raise


@dataclass
class Timeline:
    fps_num: int = 30
    fps_den: int = 1
    tracks: list[Track] = field(default_factory=list)
    markers: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.fps_num <= 0 or self.fps_den <= 0:
            raise ValueError("Invalid frame rate")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        """Build a timeline from untrusted JSON, validating every field."""
        if not isinstance(data, dict):
            raise ValueError("Invalid timeline")
        fps_num = _int(data.get('fps_num', 30), "fps_num", 1, 1_000_000)
        fps_den = _int(data.get('fps_den', 1), "fps_den", 1, 1_000_000)
        if not 1 <= fps_num / fps_den <= 240:
            raise ValueError("Invalid frame rate")
        tracks, markers = data.get('tracks', []), data.get('markers', [])
        if not isinstance(tracks, list) or len(tracks) > MAX_TRACKS:
            raise ValueError("Invalid track list")
        if not isinstance(markers, list) or len(markers) > MAX_MARKERS:
            raise ValueError("Invalid marker list")
        clean_markers = []
        for marker in markers:
            if not isinstance(marker, dict):
                raise ValueError("Invalid marker")
            clean_markers.append({'frame': _int(marker.get('frame'), "Marker frame"),
                                  'label': _str(marker.get('label', ''), "Marker label", 500)})
        return cls(fps_num=fps_num, fps_den=fps_den,
                   tracks=[_track_from_dict(t) for t in tracks], markers=clean_markers)

    @classmethod
    def from_legacy(cls, state):
        """Import version-1 editor selection without altering its source media."""
        fps = 30
        start = round(float(state.get('start', 0)) * fps)
        end = round(float(state.get('end', 0)) * fps)
        source = state.get('source', '')
        clips = [Clip(source=source, start=0, source_in=start, length=end-start)] if source and end > start else []
        return cls(tracks=[Track('video', 'Video', clips), Track('audio', 'Audio'),
                           Track('text', 'Text'), Track('overlay', 'Overlay')])
