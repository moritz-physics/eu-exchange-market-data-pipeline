# german_scraper/pipelines/save_local.py
from pathlib import Path
import json
from pathlib import Path


# Add to SaveLocalPipeline:
async def save(self, download, subdir: str):
    # download can be a Playwright Download object OR (filename, bytes) tuple
    sub = self.ROOT / subdir
    sub.mkdir(parents=True, exist_ok=True)
    if isinstance(download, tuple):
        filename, data = download
        target = sub / filename
        if self.has_seen(filename):
            print(f"⚠️  Already downloaded, skipping: {filename}")
            return None
        with open(target, "wb") as f:
            f.write(data)
        print(f"⬇️  Saved → {target}")
        self.mark_seen(filename)
        return target
    else:
        # Playwright download
        ...


class SaveLocalPipeline:
    ROOT = Path("downloads")
    MANIFEST_PATH = Path("german_scraper/core/manifest.json")

    def __init__(self):
        self.ROOT.mkdir(exist_ok=True)
        self._load_manifest()

    def _load_manifest(self):
        if self.MANIFEST_PATH.exists():
            with open(self.MANIFEST_PATH, "r", encoding="utf-8") as f:
                self.seen = set(json.load(f))
        else:
            self.seen = set()

    def _save_manifest(self):
        with open(self.MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(self.seen), f, indent=2)

    def has_seen(self, filename: str) -> bool:
        return filename in self.seen

    def mark_seen(self, filename: str):
        self.seen.add(filename)
        self._save_manifest()

    async def save(self, download, subdir: str):
        sub = self.ROOT / subdir
        sub.mkdir(parents=True, exist_ok=True)
        filename = download.suggested_filename

        if self.has_seen(filename):
            print(f"⚠️  Already downloaded, skipping: {filename}")
            return None

        target = sub / filename
        await download.save_as(target)
        print(f"⬇️  Saved → {target}")
        self.mark_seen(filename)
        return target
