from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.config import settings

db_url = settings.resolved_database_url()

connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
engine = create_engine(db_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

