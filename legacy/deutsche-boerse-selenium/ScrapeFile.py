# -*- coding: utf-8 -*-
"""
Created on Mon Apr 14 11:00:00 2025

@author: ifbla
"""

import asyncio
from ScrapeDBAsync import download_function
import nest_asyncio
from AsyncSQLiteLogWriter import AsyncSQLiteLogWriter
#nest_asyncio.apply()  # Erlaubt das erneute Verwenden des laufenden Event-Loops

async def main():
    # Erstelle den Log-Writer (achte dabei auf Batch-Größe und Flush-Intervall)
    log_writer = AsyncSQLiteLogWriter(db_path="C:/Users/ifbla/Downloads/DB_scraping/DeutscheBoerse/logging.db", batch_size=10, flush_interval=3)
    
    # Starte den Logging-Worker
    worker_task = asyncio.create_task(log_writer.worker())
    
    # Beispielhafte Aufrufe der download_function mit unterschiedlichen Parametern
    calls = [
        ("pretrade", "BoerseFrankfurt", "all"),
        ("posttrade", "BoerseFrankfurt", "all"),
        ("pretrade", "Tradegate", "all"),
        ("posttrade", "Tradegate", "all"),
        ("pretrade", "Xetra", "all"),
        ("posttrade", "Xetra", "all"),
        ("pretrade", "Eurex", "option"),
        ("pretrade", "Eurex", "non_option"),
        ("posttrade", "Eurex", "all"),
        # Füge weitere Parameter-Kombinationen hinzu
    ]

    tasks = [
        asyncio.create_task(download_function(pretrade_posttrade, baltic_nordic, asset_class, log_writer))
        for pretrade_posttrade, baltic_nordic, asset_class in calls
    ]
    
    # Warte auf alle Tasks (errors werden hier als Exception-Objekte zurückgegeben)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, res in enumerate(results):
        log_writer.log("overall","asset_main", "INFO", f"Download task {i} completed with result: {res}")
    
    # Gib dem Log-Worker noch etwas Zeit, um alle Einträge zu verarbeiten
    await asyncio.sleep(5)
    await log_writer.shutdown()
    await worker_task

if __name__ == '__main__':
    asyncio.run(main())
