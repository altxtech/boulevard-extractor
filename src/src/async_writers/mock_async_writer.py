import asyncio
from typing import Optional
import random

class MockAsyncWriter:
    def __init__(self, errors: str = 'never', latency = 0.01):
        # option to simulate exceptions 
        assert errors in ('never', 'maybe', 'always')
        self.errors = errors
        self.latency = latency # Default 10ms
        self.data = []

    async def write_rows(self, rows: dict) -> Optional[Exception]:
        # Simulate latency
        await asyncio.sleep(self.latency)
        try:
            # Simulate that it errors sometimes
            if self.errors == 'always':
                raise Exception('Always fails')
            elif self.errors == 'maybe':
                if random.random() > 0.5:
                    raise Exception('Sometimes fails')
                
            self.data.append(rows)

        except Exception as e:
            return e

        
