"""Seed script to populate initial sample incidents, KB articles, and admin account."""

import csv
import os
from app import create_app
from db import db, get_now
from models.incident import Incident
from models.kb_article import KBArticle
from models.knowledge_entry import KnowledgeEntry
from models.servicenow_group import ServiceNowGroup
from models.user import User
from services.auth_service import ADMIN_MODULES
from services.tfidf_engine import retrain

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SAMPLE_DIR = os.path.join(BASE_DIR, "sample_data")


def seed_admin():
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(username="admin", role="Admin", modules=ADMIN_MODULES)
        admin.set_password("Admin@123")
        db.session.add(admin)
        db.session.commit()
        print("  - Created default admin account (admin / Admin@123)")
    else:
        print("  - Admin user already exists")


def seed_groups():
    default_groups = [
        "Application Support",
        "DBA Team",
        "Middleware Team",
        "Unix Team",
        "Network Team",
    ]
    added = 0
    for name in default_groups:
        if not ServiceNowGroup.query.filter_by(name=name).first():
            db.session.add(ServiceNowGroup(name=name, active=True, created_at=get_now()))
            added += 1
    db.session.commit()
    print(f"  - Seeded {added} ServiceNow assignment groups")


def seed_incidents():
    csv_path = os.path.join(SAMPLE_DIR, "sample_incidents.csv")
    if not os.path.exists(csv_path):
        print("  - sample_incidents.csv not found, skipping incident seeding")
        return

    added = 0
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            number = row.get("incident_number", "").strip()
            if not number or Incident.query.filter_by(incident_number=number).first():
                continue
            db.session.add(
                Incident(
                    incident_number=number,
                    application=row.get("application", ""),
                    server=row.get("server", ""),
                    environment=row.get("environment", ""),
                    error_description=row.get("error_description", ""),
                    exception_message=row.get("exception_message", ""),
                    root_cause=row.get("root_cause", ""),
                    resolution=row.get("resolution", ""),
                    assignment_group=row.get("assignment_group", ""),
                    status=row.get("status", "Resolved"),
                    success_count=int(row.get("success_count", 1) or 1),
                    updated_at=get_now(),
                )
            )
            added += 1
    db.session.commit()
    print(f"  - Seeded {added} historical incidents from CSV")


def seed_kb_articles():
    csv_path = os.path.join(SAMPLE_DIR, "sample_kb_articles.csv")
    if not os.path.exists(csv_path):
        print("  - sample_kb_articles.csv not found, skipping KB article seeding")
        return

    added = 0
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("title", "").strip()
            if not title or KBArticle.query.filter_by(title=title).first():
                continue
            db.session.add(
                KBArticle(
                    title=title,
                    error_pattern=row.get("error_pattern", ""),
                    root_cause=row.get("root_cause", ""),
                    resolution=row.get("resolution", ""),
                    assignment_group=row.get("assignment_group", ""),
                    active=bool(int(row.get("active", 1) or 1)),
                )
            )
            added += 1
    db.session.commit()
    print(f"  - Seeded {added} KB articles from CSV")


def seed_knowledge_repo():
    if KnowledgeEntry.query.count() > 0:
        print("  - Knowledge repository entries already exist")
        return

    sample_entries = [
        {
            "pattern": "ORA-12541 TNS no listener",
            "meaning": "Oracle database listener service is stopped or unreachable on port 1521.",
            "resolution": "Log in to DB host and run 'lsnrctl status' followed by 'lsnrctl start'.",
            "assignment_group": "DBA Team",
        },
        {
            "pattern": "java.lang.OutOfMemoryError Java heap space",
            "meaning": "Application JVM heap memory exhausted during high volume processing.",
            "resolution": "Increase max heap (-Xmx) in JVM startup arguments and analyze heap dump.",
            "assignment_group": "Middleware Team",
        },
    ]
    for item in sample_entries:
        db.session.add(
            KnowledgeEntry(
                pattern=item["pattern"],
                meaning=item["meaning"],
                resolution=item["resolution"],
                assignment_group=item["assignment_group"],
                frequency=1,
                active=True,
                last_seen=get_now(),
            )
        )
    db.session.commit()
    print(f"  - Seeded {len(sample_entries)} manual knowledge repository entries")


def train_index():
    incidents = Incident.query.all()
    kb_articles = KBArticle.query.filter_by(active=True).all()
    knowledge = KnowledgeEntry.query.filter_by(active=True).all()
    count = retrain(incidents, kb_articles, knowledge)
    print(f"  - TF-IDF recommendation index retrained with {count} documents")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        print("Seeding IRR Log Analyser initial data:")
        seed_admin()
        seed_groups()
        seed_incidents()
        seed_kb_articles()
        seed_knowledge_repo()
        train_index()
        print("Seeding completed successfully.")
