# german_scraper/pipelines/save_local.py
from pathlib import Path
class SaveLocalPipeline:
    ROOT = Path("downloads")
    def __init__(self):
        self.ROOT.mkdir(exist_ok=True)
    async def save(self, download, subdir: str):
        sub = self.ROOT / subdir
        sub.mkdir(parents=True, exist_ok=True)
        target = sub / download.suggested_filename
        if target.exists():
            print(f"⚠️  Exists, skipping: {target.name}")
        else:
            await download.save_as(target)
            print(f"⬇️  Saved → {target}")
        return target
