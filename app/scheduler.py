from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.scraper import PrizePicksScraper
import logging

logger = logging.getLogger(__name__)

class DataRefreshScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.scraper = PrizePicksScraper()
        
    async def refresh_all_sports(self):
        """Refresh data for all available sports"""
        try:
            sports = self.scraper.get_sports()
            for sport in sports:
                logger.info(f"Refreshing data for sport ID: {sport.id}")
                await self.scraper.refresh_all_data(sport_id=sport.id)
                logger.info(f"Successfully refreshed data for sport ID: {sport.id}")
        except Exception as e:
            logger.error(f"Error refreshing sports data: {str(e)}")
    
    def start(self):
        """Start the scheduler"""
        # Schedule refresh every 30 minutes
        self.scheduler.add_job(
            self.refresh_all_sports,
            CronTrigger(minute='*/30'),  # Run every 30 minutes
            id='refresh_sports_data',
            name='Refresh all sports data every 30 minutes',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info("Data refresh scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Data refresh scheduler stopped") 