import sys
import os
import asyncio

# Add bot directory to sys.path so 'tools' can be imported directly
sys.path.append(os.path.join(os.getcwd(), 'bot'))

from tools.search import search_and_format

async def main():
    query = "best mewgenics cat team"
    print(f"Searching for: {query}")
    try:
        results = await search_and_format(query, num_results=5)
        print("\n--- RESULTS ---\n")
        print(results)
        print("\n---------------\n")
    except Exception as e:
        print(f"Search failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
