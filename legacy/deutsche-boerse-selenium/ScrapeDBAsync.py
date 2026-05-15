# -*- coding: utf-8 -*-
"""
Created on Mon Apr 14 10:57:12 2025

@author: ifbla
"""

import asyncio
import aiohttp
import datetime as dt
import gzip
import json
import os
import random
import re
import shutil
from selenium import webdriver
import selenium.common.exceptions as sel_except
import AsyncSQLiteLogWriter
import pytz

central_folder= "I:/BourseScraping/Data"

subgroup_exchange_2_outdir = {"BoerseFrankfurt":{
                                        "all":"/BoerseFrankfurt"
                                        },
                                    "Xetra":{
                                        "all":"/Xetra"
                                        },
                                    "Tradegate":{
                                        "all":"/Tradegate"
                                        },
                                    "Eurex":{
                                        "all":"/Eurex",
                                        "option":"/Eurex",
                                        "non_option":"/Eurex"
                                        }
                                    
                                    }

subgroup_exchange_2_web_page = {"BoerseFrankfurt":{
                                        "all":"https://mfs.deutsche-boerse.com/DFRA"
                                        },
                                    "Xetra":{
                                        "all":"https://mfs.deutsche-boerse.com/DETR"
                                        },
                                    "Tradegate":{
                                        "all":"https://mfs.deutsche-boerse.com/DGAT"
                                        },
                                    "Eurex":{
                                        "all":"https://mfs.deutsche-boerse.com/DEUR",
                                        "option":"https://mfs.deutsche-boerse.com/DEUR",
                                        "non_option":"https://mfs.deutsche-boerse.com/DEUR"
                                        }
                                    }

period_naming = {"pretrade":"pretrade",
                 "posttrade":"posttrade"}

async def download_function(pretrade_posttrade : str, exchange : str, subgroup : str, log_writer : AsyncSQLiteLogWriter):
    if pretrade_posttrade == "pretrade" and subgroup == "all" and exchange == "Eurex":
        log_writer.log(exchange,subgroup, "ERROR", "Eurex does not have combined pretrade information.")
        raise ValueError("Eurex does not have combined pretrade information.")
    

    # Download-Verzeichnis vorbereiten
    if subgroup =="all" or subgroup=="normal":
        outdir_end = pretrade_posttrade
    else:
        if subgroup == "option":
            outdir_end = pretrade_posttrade+"Opt"
        elif subgroup == "non_option":
            outdir_end = pretrade_posttrade+"NonOpt"
        else:
            subgroup_link = "Error"
    outDir = os.path.join(central_folder + subgroup_exchange_2_outdir[exchange][subgroup], outdir_end)
    intDir = central_folder + subgroup_exchange_2_outdir[exchange][subgroup]
    latest_file_storage_file = os.path.join(intDir, f"latest_download_{subgroup}_{pretrade_posttrade}.json")

    # Lese den zuletzt heruntergeladenen Dateizeiger
    with open(latest_file_storage_file, "r") as file:
        data = json.load(file)
        latest = data["latest_file_downloaded"]

    latest_time_scraped = dt.datetime.strptime(latest, "%Y-%m-%dT%H%M")
    if subgroup =="all" or subgroup=="normal":
        subgroup_link = ""
    else:
        if subgroup == "option":
            subgroup_link = "MDOptions"
        elif subgroup == "non_option":
            subgroup_link = "Others"
        else:
            subgroup_link = "Error"
    page = subgroup_exchange_2_web_page[exchange][subgroup] + "-" + period_naming[pretrade_posttrade] + subgroup_link

    # Hilfsfunktion, die den Selenium-Code synchron ausführt und mittels asyncio.to_thread asynchron aufruft
    async def get_sourcecode(page):
        def sync_get_sourcecode(page):
            driver = webdriver.Firefox()
            try:
                driver.get(page)
                # Wartezeit für die vollständige Seitendarstellung
                # (Dieser sleep erfolgt im Thread und blockiert nicht den Event-Loop)
                import time
                time.sleep(10)
                source = driver.page_source
            finally:
                driver.quit()
            return source

        return await asyncio.to_thread(sync_get_sourcecode, page)

    await asyncio.sleep(random.randint(1,60))
    while True:
        # Versuche, den Seitenquelltext (source code) asynchron zu laden – mit bis zu 3 Versuchen.
        sourcecode = None
        for i in range(3):
            try:
                sourcecode = await get_sourcecode(page)
                break
            except sel_except.WebDriverException:
                await asyncio.sleep(random.randint(10 * i, 30 * i))
        else:
            log_writer.log(exchange,subgroup, "ERROR", "Issues With Webpage after 3 attempts!")
            raise ValueError("Issues With Webpage!")

        # Erzeuge alle relevanten Download-Links aus dem Seitenquelltext
        linkHeader = 'https://mfs.deutsche-boerse.com'
        examplelink = f"https://mfs.deutsche-boerse.com/api/download/DEUR-{pretrade_posttrade}{subgroup_link}-2025-04-16T14_21.json.gz"
        noChars = len(examplelink) - len(linkHeader)
        linkIndex = [m.start() for m in re.finditer("/api/download/", sourcecode)]
        allLinks = []
        all_times = []
        for index in linkIndex:
            link = sourcecode[index:index+noChars]
            allLinks.append(link)
            time_str = sourcecode[index+noChars - len("2000-00-00T00_00")-len(".json.gz"):index+noChars-len(".json.gz")]
            all_times.append(dt.datetime.strptime(time_str, "%Y-%m-%dT%H_%M"))
        relevant_links = [allLinks[i] for i in range(len(allLinks)) if all_times[i] > latest_time_scraped]
        allFullLinks = [linkHeader + link for link in relevant_links]
        allFullLinks = [re.sub(r'amp;', '', file) for file in allFullLinks]
        allFullLinks.sort()
        allFullLinks = allFullLinks[0:100]

        # Erstelle ein Dictionary, in dem Dateiname und zugehöriger Link verknüpft sind
        exampleName = f'{pretrade_posttrade}{subgroup_link}-2024-12-12T1927.json.gz'
        noCharsName = len(exampleName)
        file_to_link = {}
        for link in allFullLinks:
            filename = link[-noCharsName-6:]
            file_to_link[filename] = link
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0"
        }

        # Falls es relevante Links gibt, lade diese asynchron herunter
        if allFullLinks:
            async with aiohttp.ClientSession(headers=headers) as session:
                for filename, link in file_to_link.items():
                    response_status = None
                    response_content = None
                    for attempt in range(3):
                        try:
                            async with session.get(link) as resp:
                                await asyncio.sleep(1)
                                if resp.status == 200:
                                    response_content = await resp.read()
                                    response_status = resp.status
                                    log_writer.log(exchange,subgroup, "INFO", f"Downloaded {filename} successfully on attempt {attempt+1}")
                                    await asyncio.sleep(random.randint(20,60))
                                    break
                                elif resp.status == 404:
                                    log_writer.log(exchange,subgroup, "WARNING", f"{filename} was not available on the webpage anymore!")
                                    response_status = resp.status
                                    await asyncio.sleep(random.randint(20,60))
                                    break
                                else:
                                    # Bei fehlerhaften HTTP-Status kann man alternativ kurz warten
                                    log_writer.log(exchange,subgroup, "WARNING", f"Non-200 status ({response_status}) for {filename} on attempt {attempt+1}")
                                    await asyncio.sleep(1)
                        except aiohttp.ClientPayloadError as e:
                            log_writer.log(exchange,subgroup, "WARNING", f"ClientPayloadError for {filename} on attempt {attempt+1}: {e}")
                            await asyncio.sleep(60 * attempt)
                    else:
                        log_writer.log(exchange,subgroup, "ERROR", f"Failed to download {filename} after 3 attempts. Retrying once more.")
                        async with session.get(link) as resp:
                            response_content = await resp.read()
                            response_status = resp.status

                    if response_status == 200:
                        tempName = os.path.join(outDir, filename)

                        # Speichere die heruntergeladene Datei (synchroner I/O)
                        try:
                            with open(tempName, 'wb') as file:
                                file.write(response_content)
                            log_writer.log(exchange,subgroup, "INFO", f"Saved file: {tempName}")
                        except Exception as e:
                            log_writer.log(exchange,subgroup, "ERROR", f"Error saving file {tempName}: {e}")
                            continue

                        latest_time_scraped = dt.datetime.strptime(filename[len("DEUR-")+len(pretrade_posttrade)+len(subgroup_link)+1:-len(".json.gz")], "%Y-%m-%dT%H_%M")
                    elif response_status == 404:
                        continue
                    else:
                        log_writer.log(exchange,subgroup, "ERROR", f"Download failed for {filename} with status {response_status}")
                        raise ValueError("Error downloading file")
            
            # Aktualisiere den 'latest'-Pointer
            to_write = {"latest_file_downloaded": latest_time_scraped.strftime("%Y-%m-%dT%H%M")}
            with open(latest_file_storage_file, "w") as f:
                json.dump(to_write, f)
                log_writer.log(exchange,subgroup, "INFO", f"Updated latest download pointer: {to_write}")
            await asyncio.sleep(random.randint(5, 15))
            if latest_time_scraped.astimezone(pytz.UTC) + dt.timedelta(minutes=60) > dt.datetime.now().astimezone(pytz.UTC):
                sleep_duration = random.randint(6900, 7100)
                log_writer.log(exchange,subgroup, "INFO", f"Sleeping for {sleep_duration} seconds as rate limiting measure.")
                await asyncio.sleep(sleep_duration)
        else:
            log_writer.log(exchange,subgroup, "INFO", "No new links found. Waiting.")
            await asyncio.sleep(random.randint(6000, 6600))

        await asyncio.sleep(random.randint(30, 60))

    return None
