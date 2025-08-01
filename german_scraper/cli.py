# german_scraper/cli.py
import asyncio
from encodings.punycode import T
from german_scraper.core.playwright_client import PlaywrightClient
from german_scraper.pipelines.save_local import SaveLocalPipeline
from german_scraper.exchanges.berlin import Berlin
from german_scraper.exchanges.lsx import LSX
from german_scraper.exchanges.munich import Munich
from german_scraper.exchanges.boersenag import BoersenAG
from german_scraper.exchanges.athex import ATHEX
from german_scraper.exchanges.bank_of_greece import BankOfGreece
from german_scraper.exchanges.bucharest import Bucharest
from german_scraper.exchanges.cboe import Cboe
from german_scraper.exchanges.bme import BME


async def main(debug=True):
    pipeline = SaveLocalPipeline()
    async with PlaywrightClient().launch() as browser:
        scrapers = [
            #BME(browser, pipeline, debug),
            #Cboe(browser, pipeline, debug),
            #BankOfGreece(browser, pipeline, debug),
            #Bucharest(browser, pipeline, debug),
            #ATHEX(browser, pipeline, debug),
            #BoersenAG(browser, pipeline, debug),
            #Berlin(browser, pipeline, debug),
            LSX(browser, pipeline, debug),
            #Munich(browser, pipeline, debug),
            
        ]
        for s in scrapers:
            print(f"\n=== {s.name} ===")
            try:
                await s.run()
            except Exception as e:
                print(f"❌ {s.name} failed: {e}")

if __name__ == "__main__":
    asyncio.run(main(debug=False))   # ← set True for dry run
