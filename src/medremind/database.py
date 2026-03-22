"""SQLAlchemy models and database session management."""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from medremind.config import settings


def _utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    medications = relationship("Medication", back_populates="person")


class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    name = Column(Text, nullable=False)
    dose = Column(Text, nullable=False)
    food_rule = Column(
        String(20), nullable=False, default="any"
    )  # before_food / after_food / with_food / empty_stomach / any
    start_date = Column(Date, default=date.today, nullable=False)
    end_date = Column(Date, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    person = relationship("Person", back_populates="medications")
    schedules = relationship(
        "Schedule", back_populates="medication", cascade="all, delete-orphan"
    )


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    medication_id = Column(Integer, ForeignKey("medications.id"), nullable=False)
    time_hhmm = Column(Text, nullable=False)  # e.g. "08:00"
    active = Column(Boolean, default=True, nullable=False)

    medication = relationship("Medication", back_populates="schedules")


_connect_args = {}
if settings.database_url.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url, echo=False, connect_args=_connect_args
)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create tables and seed persons from config if table is empty."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.query(Person).count() == 0 and settings.persons:
            db.add_all([Person(name=name) for name in settings.persons])
            db.commit()


def get_db() -> Session:
    """Get a database session."""
    return SessionLocal()
