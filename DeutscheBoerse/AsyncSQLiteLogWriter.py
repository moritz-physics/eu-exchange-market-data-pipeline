# -*- coding: utf-8 -*-
"""
Created on Mon Apr 14 12:47:06 2025

@author: ifbla
"""

import asyncio
import datetime as dt
import sqlite3

class AsyncSQLiteLogWriter:
    def __init__(self, db_path='logging.db', batch_size=20, flush_interval=5):
        """
        :param db_path: Pfad zur SQLite-Datenbank.
        :param batch_size: Anzahl von Einträgen, ab denen ein Batch-Flush erfolgt.
        :param flush_interval: Maximale Wartezeit (in Sekunden) bis zum Flush, auch wenn batch_size noch nicht erreicht ist.
        """
        self.db_path = db_path
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.queue = asyncio.Queue()
        self.running = True
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._apply_pragmas()

    def _apply_pragmas(self):
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA synchronous=NORMAL')
        self.conn.execute('PRAGMA temp_store=MEMORY')
        self.conn.commit()

    def ensure_table_exists(self, exchange:str,asset_type: str) -> str:
        """
        Stellt sicher, dass für den Asset-Type eine Tabelle existiert.
        Der Tabellenname wird als "logs_<asset_type>" definiert.
        """
        table_name = f'logs_{exchange}_{asset_type}'
        create_table_sql = f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level TEXT,
                message TEXT
            )
        '''
        self.conn.execute(create_table_sql)
        self.conn.commit()
        return table_name

    async def worker(self):
        """
        Der Worker liest Logeinträge aus der Queue und schreibt sie batchweise in die Datenbank.
        """
        batch = []
        while self.running:
            try:
                log_item = await asyncio.wait_for(self.queue.get(), timeout=self.flush_interval)
                batch.append(log_item)
                # Versuche, so viele wie möglich sofort zu entnehmen (bis zum batch_size Limit)
                while len(batch) < self.batch_size:
                    try:
                        log_item = self.queue.get_nowait()
                        batch.append(log_item)
                    except asyncio.QueueEmpty:
                        break
                await self.flush_batch(batch)
                batch = []
            except asyncio.TimeoutError:
                if batch:
                    await self.flush_batch(batch)
                    batch = []
            except Exception as e:
                print("Fehler im Log-Worker:", e)

    async def flush_batch(self, batch):
        """
        Gruppiert Logeinträge nach Asset-Type und schreibt diese batchweise in die entsprechenden Tabellen.
        :param batch: Liste von Tupeln (exchange, asset_type, timestamp, level, message)
        """
        grouped = {}
        for item in batch:
            exchange, asset_type, timestamp, level, message = item
            grouped.setdefault((exchange,asset_type), []).append((timestamp, level, message))
        
        def db_write():
            for (exchange, asset_type), logs in grouped.items():
                table_name = self.ensure_table_exists(exchange,asset_type)
                self.conn.executemany(
                    f"INSERT INTO {table_name} (timestamp, level, message) VALUES (?, ?, ?)",
                    logs
                )
            self.conn.commit()
        
        await asyncio.to_thread(db_write)

    def log(self, exchange:str ,asset_type: str, level: str, message: str):
        """
        Fügt einen Logeintrag der Queue hinzu.
        :param exchange: z.B. "nordic"
        :param asset_type: z. B. "equities" (wird zur Tabellenauswahl verwendet)
        :param level: Log-Level (wie "INFO", "WARNING", "ERROR")
        :param message: Log-Nachricht
        """
        timestamp = dt.datetime.now().isoformat()
        self.queue.put_nowait((exchange, asset_type, timestamp, level, message))

    async def shutdown(self):
        """
        Stoppt den Worker, leert die Queue und schließt die Datenbankverbindung.
        """
        self.running = False
        batch = []
        while not self.queue.empty():
            batch.append(self.queue.get_nowait())
        if batch:
            await self.flush_batch(batch)
        await asyncio.to_thread(self.conn.close)