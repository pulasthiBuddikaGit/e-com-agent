import asyncio
import json

from backend.config import get_settings
from backend.kapruka_mcp import KaprukaMCPClient


async def main():
    client = KaprukaMCPClient(get_settings())
    tools = await client.list_tools()
    print(json.dumps(tools, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
