"""Playlist and timed player logic (no rendering, no network sources).

NDI and other live sources need an SDK and a display path the clone does not have, so they
raise UnsupportedSource instead of pretending to play.
"""
import json
from dataclasses import dataclass
from pathlib import Path


class PlaylistError(Exception):
    pass


class UnsupportedSource(PlaylistError):
    pass


@dataclass
class Item:
    path: str
    duration: float


class Playlist:
    def __init__(self):
        self.items = []

    def add(self, path, duration):
        path = str(path)
        if "://" in path:
            raise UnsupportedSource(f"live/network source not supported: {path}")
        if not Path(path).is_file():
            raise PlaylistError(f"file not found: {path}")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise PlaylistError("duration must be > 0")
        self.items.append(Item(path, float(duration)))

    def save(self, path):
        data = [{"path": i.path, "duration": i.duration} for i in self.items]
        Path(path).write_text(json.dumps({"items": data}, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            pl = cls()
            for d in data["items"]:
                pl.add(d["path"], d["duration"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise PlaylistError(f"cannot read playlist {path}: {e}") from e
        return pl


class Player:
    def __init__(self, playlist, loop=False):
        if not playlist.items:
            raise PlaylistError("playlist is empty")
        self.playlist = playlist
        self.loop = loop
        self.index = 0
        self.elapsed = 0.0
        self.finished = False

    @property
    def current(self):
        return None if self.finished else self.playlist.items[self.index]

    def next(self):
        self.elapsed = 0.0
        n = len(self.playlist.items)
        if self.index + 1 < n:
            self.index += 1
        elif self.loop:
            self.index = 0
        else:
            self.finished = True
            return None
        return self.current

    def prev(self):
        self.elapsed = 0.0
        self.finished = False
        n = len(self.playlist.items)
        if self.index > 0:
            self.index -= 1
        elif self.loop:
            self.index = n - 1
        return self.current

    def tick(self, dt):
        """Advance playback time by dt seconds; may advance several items."""
        if dt < 0:
            raise PlaylistError("dt must be >= 0")
        self.elapsed += dt
        while not self.finished and self.elapsed >= self.current.duration:
            self.elapsed -= self.current.duration
            carry = self.elapsed
            self.next()
            self.elapsed = carry
        return self.current
