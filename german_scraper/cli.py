# german_scraper/cli.py
import asyncio
from german_scraper.core.playwright_client import PlaywrightClient
from german_scraper.pipelines.save_local import SaveLocalPipeline
from german_scraper.exchanges.berlin import Berlin
from german_scraper.exchanges.lsx import LSX
from german_scraper.exchanges.munich import Munich

async def main(debug=True):
    pipeline = SaveLocalPipeline()
    async with PlaywrightClient().launch() as browser:
        scrapers = [
            Berlin(browser, pipeline, debug),
            LSX(browser, pipeline, debug),
            Munich(browser, pipeline, debug),
        ]
        for s in scrapers:
            print(f"\n=== {s.name} ===")
            try:
                await s.run()
            except Exception as e:
                print(f"❌ {s.name} failed: {e}")

if __name__ == "__main__":
    asyncio.run(main(debug=True))   # ← set True for dry-run
