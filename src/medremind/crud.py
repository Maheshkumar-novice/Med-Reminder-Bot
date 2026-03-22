"""Database CRUD operations."""

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from medremind.database import Medication, Person, Schedule


def get_persons(db: Session) -> list[Person]:
    """Get all active persons."""
    return db.query(Person).filter(Person.active.is_(True)).all()


def add_person(db: Session, name: str) -> Person | None:
    """Add a new person. Returns None if name already exists (case-insensitive)."""
    existing = db.query(Person).filter(func.lower(Person.name) == name.lower()).first()
    if existing:
        return None
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def add_medication(
    db: Session,
    person_id: int,
    name: str,
    dose: str,
    food_rule: str,
    times: list[str],
) -> Medication:
    """Add a medication with its schedule times."""
    med = Medication(
        person_id=person_id,
        name=name,
        dose=dose,
        food_rule=food_rule,
    )
    db.add(med)
    db.flush()

    for t in times:
        db.add(Schedule(medication_id=med.id, time_hhmm=t))

    db.commit()
    db.refresh(med)
    return med


def list_medications(db: Session) -> list[Medication]:
    """List all medications (active and paused) with schedules and person."""
    return (
        db.query(Medication)
        .options(joinedload(Medication.person), joinedload(Medication.schedules))
        .order_by(Medication.person_id, Medication.name)
        .all()
    )


def get_active_medications(db: Session) -> list[Medication]:
    """Get only active medications."""
    return (
        db.query(Medication)
        .filter(Medication.active.is_(True))
        .options(joinedload(Medication.person), joinedload(Medication.schedules))
        .order_by(Medication.person_id, Medication.name)
        .all()
    )


def get_paused_medications(db: Session) -> list[Medication]:
    """Get only paused medications."""
    return (
        db.query(Medication)
        .filter(Medication.active.is_(False))
        .options(joinedload(Medication.person), joinedload(Medication.schedules))
        .order_by(Medication.person_id, Medication.name)
        .all()
    )


def pause_medication(db: Session, med_id: int) -> Medication | None:
    """Pause a medication and its schedules."""
    med = db.query(Medication).filter(Medication.id == med_id).first()
    if not med:
        return None
    med.active = False
    for s in med.schedules:
        s.active = False
    db.commit()
    db.refresh(med)
    return med


def resume_medication(db: Session, med_id: int) -> Medication | None:
    """Resume a paused medication and its schedules."""
    med = db.query(Medication).filter(Medication.id == med_id).first()
    if not med:
        return None
    med.active = True
    for s in med.schedules:
        s.active = True
    db.commit()
    db.refresh(med)
    return med


def delete_medication(db: Session, med_id: int) -> bool:
    """Permanently delete a medication and its schedules."""
    med = db.query(Medication).filter(Medication.id == med_id).first()
    if not med:
        return False
    db.delete(med)
    db.commit()
    return True


def get_medication_with_schedules(db: Session, med_id: int) -> Medication | None:
    """Get a single medication with its schedules and person loaded."""
    return (
        db.query(Medication)
        .filter(Medication.id == med_id)
        .options(joinedload(Medication.person), joinedload(Medication.schedules))
        .first()
    )


def get_active_schedules(db: Session) -> list[Schedule]:
    """Get all active schedules with medication and person info."""
    return (
        db.query(Schedule)
        .join(Medication)
        .filter(Medication.active.is_(True), Schedule.active.is_(True))
        .options(
            joinedload(Schedule.medication).joinedload(Medication.person),
        )
        .all()
    )
