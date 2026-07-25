"""
Seed script to create initial admin user
Run: python seed_admin.py
"""
import os
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

# Import models from main.py (simplified inline for seeding)
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), default="Admin")
    created_at = Column(DateTime(timezone=True), default=func.now())

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/nudesignink")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@nudesignink.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def seed_admin():
    db = SessionLocal()

    # Check if admin exists
    existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if existing:
        print(f"Admin user {ADMIN_EMAIL} already exists.")
        return

    admin = User(
        email=ADMIN_EMAIL,
        password_hash=pwd_context.hash(ADMIN_PASSWORD),
        name="Admin"
    )
    db.add(admin)
    db.commit()
    print(f"✅ Admin user created: {ADMIN_EMAIL}")
    print(f"   Password: {ADMIN_PASSWORD}")
    print("   Change this password after first login!")

if __name__ == "__main__":
    seed_admin()
