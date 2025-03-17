import asyncio
import os 
import json 
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig, LLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

URL_TO_SCRAPE = 'https://app.prizepicks.com'


INSTRUCTIONS_TO_LLM = "Extract all the player information and their projection points with sports teams and leagues"

class Player(BaseModel):
    name: str = Field(description="The name of the player")
    team: str = Field(description="The team of the player")
    team_against: str = Field(description="The team the player is playing against")
    projection: float = Field(description="The projection points of the player")

async def main():
    llm_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(provider="deepseek/deepseek-chat", api_token=os.getenv("DEEPSEEK_API_KEY")),
        schema=Player.model_json_schema(),
        instructions=INSTRUCTIONS_TO_LLM,
        chunk_token_threshold=1000,
        overlap_rate=0.0,
        apply_chunking=True,
        input_format="markdown",
        extra_args={"temperature": 0.0, "max_tokens": 1000},
    )

    crawl_config = CrawlerRunConfig(
        extraction_strategy=llm_strategy,
        cache_mode=CacheMode.BYPASS, 
        process_iframes=False, 
        remove_overlay_elements=True, 
        exclude_external_links=True, 
        wait_until="networkidle"
    )

    browser_cfg = BrowserConfig(headless=True, verbose=True)

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        result = await crawler.arun(url=URL_TO_SCRAPE, config=crawl_config)
        if result.success:
            data = json.loads(result.extracted_content)
            print("Extracted data: ", data)
            llm_strategy.show_usage()
        else: 
            print("Error: " + result.error)

if __name__ == "__main__":
    asyncio.run(main())

