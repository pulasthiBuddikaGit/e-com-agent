import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    async with streamable_http_client("https://mcp.kapruka.com/mcp") as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:

            print("Initializing session...")

            await session.initialize()

            print("Connected!")

            tools = await session.list_tools()

            print("\nAvailable tools:\n")

            for tool in tools.tools:
                print(f"- {tool.name}")
                print(f"  {tool.description}\n")


if __name__ == "__main__":
    asyncio.run(main())