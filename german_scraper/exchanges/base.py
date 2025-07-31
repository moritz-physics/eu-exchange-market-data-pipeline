# german_scraper/exchanges/base.py
from abc import ABC, abstractmethod
class Exchange(ABC):
    name: str
    def __init__(self, browser, pipeline, debug=True):
        self.browser = browser
        self.pipeline = pipeline
        self.debug = debug
    @abstractmethod
    async def run(self): ...
