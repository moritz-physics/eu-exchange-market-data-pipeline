# german_scraper/exchanges/boersenag.py

import re
from .base import Exchange
from german_scraper.core.utils import click_first_consent

class BoersenAG(Exchange):
    name = "Börsen AG (Düsseldorf/Hamburg/Hannover etc.)"

    async def run(self):
        results = []
        page = await self.client.new_page()
        await page.goto("https://www.boersenag.de/mifid-ii-delayed-data/")
        await click_first_consent(page)

        # Optional unlock button
        unlock = page.get_by_role("button", name=re.compile("(Inhalt|Entsperren|Anzeigen|Zustimmen)", re.I))
        if await unlock.is_visible():
            await unlock.click()

        # --- Correct way to access iframe: page.frame(name=…) ---
        iframe = page.frame(name="mifid-iframe")

        link_selector = re.compile(r"Download der Daten für ", re.I)
        links = await iframe.locator("a").filter(has_text=link_selector).all()

        for link in links:
            label = (await link.text_content()).strip()
            if self.debug:
                print(f"(DEBUG) Would download {label}")
            else:
                async with link.page.expect_download() as dl_info:
                    await link.click()
                download = await dl_info.value
                path = await self.pipeline.save(download, "boersenag")
                results.append({"file": path, "source_link": label})

        await page.close()
        return results
