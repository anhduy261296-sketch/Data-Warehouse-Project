from __future__ import annotations

from pathlib import Path

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    def url(self, name: str) -> str:
        url = super().url(name)
        path = finders.find(name)
        if not path:
            return url
        try:
            return f'{url}?v={int(Path(path).stat().st_mtime)}'
        except OSError:
            return url
