# scheduler.py

from apscheduler.schedulers.blocking import BlockingScheduler
from app import scheduled_job
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the scheduler
scheduler = BlockingScheduler()

# Add your scheduled job
scheduler.add_job(scheduled_job, 'interval', seconds=60)  # Adjust the interval as needed

if __name__ == '__main__':
    try:
        logger.info("Starting scheduler...")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
