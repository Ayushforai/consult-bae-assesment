import sys
from pathlib import Path
from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, inspect, create_engine
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from merge import Base

DB_PATH = f"sqlite:///{ROOT_DIR / 'consultbae.db'}"
engine = create_engine(DB_PATH)


class AudioSubmission(Base):
    __tablename__ = 'audio_submissions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, ForeignKey('people.id'))
    applicant_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    duration_seconds = Column(Float)
    sample_rate_hz = Column(Integer)
    bitrate_kbps = Column(Float)
    loudness_db = Column(Float)
    snr_db = Column(Float)
    quality_label = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


def ensure_audio_schema():
    expected_columns = {col.name for col in AudioSubmission.__table__.columns}
    inspector = inspect(engine)
    if 'audio_submissions' in inspector.get_table_names():
        existing_columns = {col['name'] for col in inspector.get_columns('audio_submissions')}
        if existing_columns != expected_columns:
            AudioSubmission.__table__.drop(engine, checkfirst=True)
    Base.metadata.create_all(engine)


ensure_audio_schema()
Session = sessionmaker(bind=engine)
