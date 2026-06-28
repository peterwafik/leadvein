from __future__ import annotations

from sqlmodel import Session, select

from app.core.db import LeadCategory, CategoryMapping

# generic business taxonomy (label, key) — vertical-AGNOSTIC; admins extend at runtime
SEED_CATEGORIES = [
    ("Restaurant", "restaurant"), ("Takeaway", "takeaway"), ("Cafe", "cafe"),
    ("Bakery", "bakery"), ("Bar", "bar"), ("Pub", "pub"), ("Hotel", "hotel"),
    ("Gym", "gym"), ("Fitness Studio", "fitness_studio"), ("Hair Salon", "hair_salon"),
    ("Barber Shop", "barber_shop"), ("Nail Salon", "nail_salon"), ("Spa", "spa"),
    ("Dental Clinic", "dental_clinic"), ("Medical Clinic", "medical_clinic"),
    ("Car Wash", "car_wash"), ("Auto Repair", "auto_repair"),
    ("Convenience Store", "convenience_store"), ("Supermarket", "supermarket"),
    ("Laundromat", "laundromat"), ("Dry Cleaner", "dry_cleaner"),
    ("Butcher", "butcher"), ("Florist", "florist"), ("Pharmacy", "pharmacy"),
    ("Clothing Store", "clothing_store"), ("Hardware Store", "hardware_store"),
    ("Warehouse", "warehouse"), ("Manufacturer", "manufacturer"),
    ("Construction Company", "construction"), ("Real Estate Agency", "real_estate"),
    ("Accountant", "accountant"), ("Law Firm", "law_firm"),
    ("Marketing Agency", "marketing_agency"), ("Recruitment Agency", "recruitment"),
    ("Nursery", "nursery"), ("Cleaning Company", "cleaning"),
]


def upsert_category(session: Session, key: str, label: str,
                    parent_key: str | None = None) -> LeadCategory:
    existing = session.exec(select(LeadCategory).where(LeadCategory.key == key)).first()
    if existing:
        existing.label = label
        session.add(existing)
        session.commit()
        return existing
    parent_id = None
    if parent_key:
        parent = session.exec(select(LeadCategory).where(LeadCategory.key == parent_key)).first()
        parent_id = parent.id if parent else None
    cat = LeadCategory(key=key, label=label, parent_id=parent_id)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat


def seed_taxonomy(session: Session) -> None:
    for label, key in SEED_CATEGORIES:
        if not session.exec(select(LeadCategory).where(LeadCategory.key == key)).first():
            session.add(LeadCategory(key=key, label=label))
    session.commit()


def all_categories(session: Session) -> list[dict]:
    rows = session.exec(select(LeadCategory)).all()
    return [{"id": c.id, "key": c.key, "label": c.label, "parent_id": c.parent_id}
            for c in rows]


def category_by_key(session: Session, key: str) -> LeadCategory | None:
    return session.exec(select(LeadCategory).where(LeadCategory.key == key)).first()


def add_mapping(session: Session, source_key: str, external_value: str,
                category_key: str) -> None:
    session.add(CategoryMapping(source_key=source_key, external_value=external_value,
                                category_key=category_key))
    session.commit()


def categories_for_external(session: Session, source_key: str,
                            external_value: str) -> list[str]:
    rows = session.exec(
        select(CategoryMapping).where(CategoryMapping.source_key == source_key,
                                      CategoryMapping.external_value == external_value)).all()
    return [r.category_key for r in rows]
