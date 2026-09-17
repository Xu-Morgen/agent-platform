import asyncio
from cancel_running import case

asyncio.run(case('timeout'))
asyncio.run(case('disconnect'))
