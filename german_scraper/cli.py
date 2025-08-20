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
from german_scraper.exchanges.wienerboerse import WienerBoerse
from german_scraper.exchanges.berlin_cron import BerlinCron
from german_scraper.exchanges.ice import ICE
from german_scraper.exchanges.ice_post import ICEPost
from german_scraper.exchanges.wienerboerse_stealth import WienerBoerseStealth
from german_scraper.exchanges.luxse import LuxSE
from german_scraper.exchanges.bratislava import Bratislava

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
            #Berlin(browser, pipeline, debug),  #works quite well, but might need some robustness work
            #LSX(browser, pipeline, debug),     #works quite well, but might need some robustness work
            #Munich(browser, pipeline, debug),  #feedback wanted for real download process, couldn´t test, bc files are too large
            #WienerBoerse(browser, pipeline, debug), #UNSTABLE because of the reCAPTCHA
            #ICE(browser, pipeline, debug),    # has a two facor authentication, so terminal will aks you for PW
            #BerlinCron(browser, pipeline, debug),
            ICEPost(browser, pipeline, debug),
            LuxSE(browser, pipeline, debug),
            #Bratislava(browser, pipeline, debug), probably still unstable 
            #WienerBoerseStealth(browser, pipeline, debug),
            

            
        ]
        for s in scrapers:
            print(f"\n=== {s.name} ===")
            try:
                await s.run()
            except Exception as e:
                print(f"❌ {s.name} failed: {e}")

if __name__ == "__main__":
    asyncio.run(main(debug=True))   # ← set True for dry run
