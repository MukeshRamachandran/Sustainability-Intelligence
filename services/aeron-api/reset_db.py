import os
from backend.database.models import Base
from backend.database.connection import engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Dropping all existing database tables...")
    Base.metadata.drop_all(bind=engine)
    
    logger.info("Recreating database tables with the correct schema...")
    Base.metadata.create_all(bind=engine)
    
    logger.info("Database reset successfully! You can now start the server.")
