"""
Nu Design Ink AI - FastAPI Backend
====================================
Handles: Auth, Calendar, Voice Session, Admin APIs
"""

import os
import json
import uuid
from datetime import date, datetime, timedelta, time
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from passlib.context import CryptContext
import jwt
import httpx
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Date, Time, Text, DateTime, UUID, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# ============================================
# CONFIGURATION
# ============================================
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/nudesignink")
JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-jwt-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# ============================================
# DATABASE SETUP
# ============================================
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), default="Admin")
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now())

class WeeklySchedule(Base):
    __tablename__ = "weekly_schedules"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day_of_week = Column(Integer, nullable=False, unique=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    slot_duration_minutes = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now())

class BlockedSlot(Base):
    __tablename__ = "blocked_slots"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    block_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    reason = Column(String(255), default="Blocked")
    created_at = Column(DateTime(timezone=True), default=func.now())

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(20))
    appointment_date = Column(Date, nullable=False)
    appointment_time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, default=30)
    status = Column(String(20), default="confirmed")
    notes = Column(Text)
    source = Column(String(20), default="voice")
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now())

class VoiceSetting(Base):
    __tablename__ = "voice_settings"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voice_name = Column(String(50), default="alloy")
    greeting_script = Column(Text, default="Hi, thanks for calling Nu Design Ink.")
    personality_tone = Column(String(50), default="professional")
    speaking_pace = Column(String(20), default="normal")
    updated_at = Column(DateTime(timezone=True), default=func.now())

class FAQ(Base):
    __tablename__ = "faqs"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    category = Column(String(50), default="general")
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now())

class BusinessInfo(Base):
    __tablename__ = "business_info"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    info_key = Column(String(100), unique=True, nullable=False)
    info_value = Column(Text, nullable=False)
    category = Column(String(50), default="general")
    updated_at = Column(DateTime(timezone=True), default=func.now())

# ============================================
# PYDANTIC SCHEMAS
# ============================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class WeeklyScheduleCreate(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: str  # "HH:MM"
    end_time: str
    slot_duration_minutes: int = Field(..., ge=30, le=60)
    is_active: bool = True

class BlockSlotCreate(BaseModel):
    block_date: date
    start_time: str
    end_time: str
    reason: str = "Blocked"

class AppointmentCreate(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    appointment_date: date
    appointment_time: str
    duration_minutes: int = 30
    notes: Optional[str] = None
    source: str = "web"

class AppointmentUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None

class VoiceSettingsUpdate(BaseModel):
    voice_name: Optional[str] = None
    greeting_script: Optional[str] = None
    personality_tone: Optional[str] = None
    speaking_pace: Optional[str] = None

class FAQCreate(BaseModel):
    question: str
    answer: str
    category: str = "general"
    priority: int = 0

class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None

class BusinessInfoUpdate(BaseModel):
    info_value: str

class AvailabilityRequest(BaseModel):
    check_date: date

class AvailabilityResponse(BaseModel):
    date: date
    available_slots: List[str]
    is_open: bool

class BookingRequest(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    booking_date: date
    booking_time: str
    duration_minutes: int = 30

class BookingResponse(BaseModel):
    success: bool
    appointment_id: Optional[str] = None
    message: str

class VoiceSessionResponse(BaseModel):
    session_token: str
    expires_at: datetime

# ============================================
# DEPENDENCIES
# ============================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(payload: dict = Depends(verify_token), db: Session = Depends(get_db)) -> User:
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# ============================================
# FASTAPI APP
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown

app = FastAPI(
    title="Nu Design Ink AI API",
    description="Backend for AI-powered booking and admin dashboard",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# AUTH ENDPOINTS
# ============================================

@app.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not pwd_context.verify(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user.email, "name": user.name})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {"email": current_user.email, "name": current_user.name}

# ============================================
# VOICE SESSION ENDPOINTS
# ============================================

@app.post("/voice/session", response_model=VoiceSessionResponse)
async def create_voice_session(db: Session = Depends(get_db)):
    """Create ephemeral OpenAI Realtime session token"""
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")

    # Get voice settings for system prompt
    voice_settings = db.query(VoiceSetting).first()
    if not voice_settings:
        voice_settings = VoiceSetting()

    # Get business info for context
    business_info = db.query(BusinessInfo).all()
    business_context = "\n".join([f"{b.info_key}: {b.info_value}" for b in business_info])

    # Get active FAQs
    faqs = db.query(FAQ).filter(FAQ.is_active == True).order_by(FAQ.priority.desc()).all()
    faq_context = "\n".join([f"Q: {f.question}\nA: {f.answer}" for f in faqs])

    # Build system prompt
    system_prompt = f"""You are the AI booking assistant for Nu Design Ink, a web design and AI automation agency in the Greater Toronto Area.

VOICE: {voice_settings.voice_name}
PERSONALITY: {voice_settings.personality_tone}
PACE: {voice_settings.speaking_pace}

GREETING: {voice_settings.greeting_script}

BUSINESS INFORMATION:
{business_context}

FREQUENTLY ASKED QUESTIONS:
{faq_context}

BOOKING RULES:
- Check availability using check_availability tool before suggesting times
- Only confirm bookings when book_appointment tool returns success
- Collect name, email, and optionally phone before booking
- If no slots available, offer the next available day
- Be friendly, professional, and concise
- For questions not in FAQs, say you\'ll pass the message to the team
"""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": voice_settings.voice_name,
                "instructions": system_prompt,
                "tools": [
                    {
                        "type": "function",
                        "name": "check_availability",
                        "description": "Check available appointment slots for a specific date",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date": {
                                    "type": "string",
                                    "description": "Date to check in YYYY-MM-DD format"
                                }
                            },
                            "required": ["date"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "book_appointment",
                        "description": "Book an appointment for a client",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "email": {"type": "string"},
                                "phone": {"type": "string"},
                                "date": {"type": "string", "description": "YYYY-MM-DD"},
                                "time": {"type": "string", "description": "HH:MM"},
                                "duration_minutes": {"type": "integer", "default": 30}
                            },
                            "required": ["name", "email", "date", "time"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "get_services",
                        "description": "Get list of services offered",
                        "parameters": {"type": "object", "properties": {}}
                    }
                ]
            }
        )

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {response.text}")

    session_data = response.json()
    return {
        "session_token": session_data["client_secret"]["value"],
        "expires_at": datetime.utcnow() + timedelta(minutes=10)
    }

# ============================================
# VOICE TOOLS (Called by OpenAI Realtime)
# ============================================

@app.post("/voice/tools/check_availability")
def voice_check_availability(request: AvailabilityRequest, db: Session = Depends(get_db)):
    """Check available slots for a date"""
    day_of_week = request.check_date.weekday()

    schedule = db.query(WeeklySchedule).filter(
        WeeklySchedule.day_of_week == day_of_week,
        WeeklySchedule.is_active == True
    ).first()

    if not schedule:
        return AvailabilityResponse(
            date=request.check_date,
            available_slots=[],
            is_open=False
        )

    # Check if entire day blocked
    full_day_block = db.query(BlockedSlot).filter(
        BlockedSlot.block_date == request.check_date,
        BlockedSlot.start_time <= schedule.start_time,
        BlockedSlot.end_time >= schedule.end_time
    ).first()

    if full_day_block:
        return AvailabilityResponse(
            date=request.check_date,
            available_slots=[],
            is_open=False
        )

    # Generate slots
    slots = []
    current = datetime.combine(request.check_date, schedule.start_time)
    end = datetime.combine(request.check_date, schedule.end_time)
    duration = timedelta(minutes=schedule.slot_duration_minutes)

    while current < end:
        slot_time = current.time()

        # Check blocked
        blocked = db.query(BlockedSlot).filter(
            BlockedSlot.block_date == request.check_date,
            BlockedSlot.start_time <= slot_time,
            BlockedSlot.end_time > slot_time
        ).first()

        # Check existing appointment
        booked = db.query(Appointment).filter(
            Appointment.appointment_date == request.check_date,
            Appointment.appointment_time == slot_time,
            Appointment.status == "confirmed"
        ).first()

        if not blocked and not booked:
            slots.append(slot_time.strftime("%H:%M"))

        current += duration

    return AvailabilityResponse(
        date=request.check_date,
        available_slots=slots,
        is_open=len(slots) > 0
    )

@app.post("/voice/tools/book_appointment")
def voice_book_appointment(request: BookingRequest, db: Session = Depends(get_db)):
    """Book an appointment"""
    # Verify slot is still available
    existing = db.query(Appointment).filter(
        Appointment.appointment_date == request.booking_date,
        Appointment.appointment_time == datetime.strptime(request.booking_time, "%H:%M").time(),
        Appointment.status == "confirmed"
    ).first()

    if existing:
        return BookingResponse(
            success=False,
            message="That slot is no longer available. Please choose another time."
        )

    appointment = Appointment(
        name=request.name,
        email=request.email,
        phone=request.phone,
        appointment_date=request.booking_date,
        appointment_time=datetime.strptime(request.booking_time, "%H:%M").time(),
        duration_minutes=request.duration_minutes,
        status="confirmed",
        source="voice"
    )

    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    return BookingResponse(
        success=True,
        appointment_id=str(appointment.id),
        message=f"Great! Your appointment is confirmed for {request.booking_date} at {request.booking_time}. We\'ll send a confirmation to {request.email}."
    )

@app.post("/voice/tools/get_services")
def voice_get_services(db: Session = Depends(get_db)):
    """Get services info"""
    services = db.query(BusinessInfo).filter(BusinessInfo.category == "services").all()
    return {"services": [{"name": s.info_key, "description": s.info_value} for s in services]}

# ============================================
# CALENDAR ENDPOINTS
# ============================================

@app.get("/calendar/weekly")
def get_weekly_calendar(
    start_date: date,
    end_date: date,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get calendar data for date range"""
    appointments = db.query(Appointment).filter(
        Appointment.appointment_date >= start_date,
        Appointment.appointment_date <= end_date
    ).order_by(Appointment.appointment_date, Appointment.appointment_time).all()

    blocked = db.query(BlockedSlot).filter(
        BlockedSlot.block_date >= start_date,
        BlockedSlot.block_date <= end_date
    ).all()

    return {
        "appointments": [
            {
                "id": str(a.id),
                "name": a.name,
                "email": a.email,
                "phone": a.phone,
                "date": a.appointment_date.isoformat(),
                "time": a.appointment_time.strftime("%H:%M"),
                "duration": a.duration_minutes,
                "status": a.status,
                "notes": a.notes,
                "source": a.source
            }
            for a in appointments
        ],
        "blocked_slots": [
            {
                "id": str(b.id),
                "date": b.block_date.isoformat(),
                "start": b.start_time.strftime("%H:%M"),
                "end": b.end_time.strftime("%H:%M"),
                "reason": b.reason
            }
            for b in blocked
        ]
    }

@app.get("/calendar/availability")
def get_availability(
    check_date: date,
    db: Session = Depends(get_db)
):
    """Public endpoint to check available slots"""
    day_of_week = check_date.weekday()

    schedule = db.query(WeeklySchedule).filter(
        WeeklySchedule.day_of_week == day_of_week,
        WeeklySchedule.is_active == True
    ).first()

    if not schedule:
        return {"date": check_date.isoformat(), "slots": [], "is_open": False}

    slots = []
    current = datetime.combine(check_date, schedule.start_time)
    end = datetime.combine(check_date, schedule.end_time)
    duration = timedelta(minutes=schedule.slot_duration_minutes)

    while current < end:
        slot_time = current.time()

        blocked = db.query(BlockedSlot).filter(
            BlockedSlot.block_date == check_date,
            BlockedSlot.start_time <= slot_time,
            BlockedSlot.end_time > slot_time
        ).first()

        booked = db.query(Appointment).filter(
            Appointment.appointment_date == check_date,
            Appointment.appointment_time == slot_time,
            Appointment.status == "confirmed"
        ).first()

        if not blocked and not booked:
            slots.append(slot_time.strftime("%H:%M"))

        current += duration

    return {"date": check_date.isoformat(), "slots": slots, "is_open": len(slots) > 0}

@app.post("/calendar/block")
def block_slot(
    request: BlockSlotCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Block a time slot"""
    blocked = BlockedSlot(
        block_date=request.block_date,
        start_time=datetime.strptime(request.start_time, "%H:%M").time(),
        end_time=datetime.strptime(request.end_time, "%H:%M").time(),
        reason=request.reason
    )
    db.add(blocked)
    db.commit()
    db.refresh(blocked)
    return {"id": str(blocked.id), "message": "Slot blocked successfully"}

@app.delete("/calendar/block/{block_id}")
def unblock_slot(
    block_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a block"""
    blocked = db.query(BlockedSlot).filter(BlockedSlot.id == uuid.UUID(block_id)).first()
    if not blocked:
        raise HTTPException(status_code=404, detail="Block not found")
    db.delete(blocked)
    db.commit()
    return {"message": "Slot unblocked"}

@app.get("/calendar/schedule")
def get_weekly_schedule(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get weekly recurring schedule"""
    schedules = db.query(WeeklySchedule).order_by(WeeklySchedule.day_of_week).all()
    return {
        "schedules": [
            {
                "id": str(s.id),
                "day": s.day_of_week,
                "day_name": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][s.day_of_week],
                "start": s.start_time.strftime("%H:%M"),
                "end": s.end_time.strftime("%H:%M"),
                "slot_duration": s.slot_duration_minutes,
                "is_active": s.is_active
            }
            for s in schedules
        ]
    }

@app.post("/calendar/schedule")
def update_weekly_schedule(
    request: WeeklyScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update weekly schedule for a day"""
    schedule = db.query(WeeklySchedule).filter(
        WeeklySchedule.day_of_week == request.day_of_week
    ).first()

    if schedule:
        schedule.start_time = datetime.strptime(request.start_time, "%H:%M").time()
        schedule.end_time = datetime.strptime(request.end_time, "%H:%M").time()
        schedule.slot_duration_minutes = request.slot_duration_minutes
        schedule.is_active = request.is_active
    else:
        schedule = WeeklySchedule(
            day_of_week=request.day_of_week,
            start_time=datetime.strptime(request.start_time, "%H:%M").time(),
            end_time=datetime.strptime(request.end_time, "%H:%M").time(),
            slot_duration_minutes=request.slot_duration_minutes,
            is_active=request.is_active
        )
        db.add(schedule)

    db.commit()
    db.refresh(schedule)
    return {"message": "Schedule updated"}

# ============================================
# APPOINTMENT ENDPOINTS
# ============================================

@app.post("/appointments")
def create_appointment(
    request: AppointmentCreate,
    db: Session = Depends(get_db)
):
    """Create appointment (public, from web form)"""
    appointment = Appointment(
        name=request.name,
        email=request.email,
        phone=request.phone,
        appointment_date=request.appointment_date,
        appointment_time=datetime.strptime(request.appointment_time, "%H:%M").time(),
        duration_minutes=request.duration_minutes,
        notes=request.notes,
        source=request.source
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return {"id": str(appointment.id), "message": "Appointment created"}

@app.get("/appointments")
def list_appointments(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List appointments with filters"""
    query = db.query(Appointment)
    if date_from:
        query = query.filter(Appointment.appointment_date >= date_from)
    if date_to:
        query = query.filter(Appointment.appointment_date <= date_to)

    apps = query.order_by(Appointment.appointment_date, Appointment.appointment_time).all()
    return {
        "appointments": [
            {
                "id": str(a.id),
                "name": a.name,
                "email": a.email,
                "phone": a.phone,
                "date": a.appointment_date.isoformat(),
                "time": a.appointment_time.strftime("%H:%M"),
                "duration": a.duration_minutes,
                "status": a.status,
                "notes": a.notes,
                "source": a.source
            }
            for a in apps
        ]
    }

@app.patch("/appointments/{appointment_id}")
def update_appointment(
    appointment_id: str,
    request: AppointmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update appointment status or notes"""
    appointment = db.query(Appointment).filter(Appointment.id == uuid.UUID(appointment_id)).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if request.status:
        appointment.status = request.status
    if request.notes is not None:
        appointment.notes = request.notes

    db.commit()
    return {"message": "Appointment updated"}

@app.delete("/appointments/{appointment_id}")
def delete_appointment(
    appointment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel/delete appointment"""
    appointment = db.query(Appointment).filter(Appointment.id == uuid.UUID(appointment_id)).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    appointment.status = "cancelled"
    db.commit()
    return {"message": "Appointment cancelled"}

# ============================================
# ADMIN: VOICE SETTINGS
# ============================================

@app.get("/admin/settings/voice")
def get_voice_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get voice settings"""
    settings = db.query(VoiceSetting).first()
    if not settings:
        settings = VoiceSetting()
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return {
        "voice_name": settings.voice_name,
        "greeting_script": settings.greeting_script,
        "personality_tone": settings.personality_tone,
        "speaking_pace": settings.speaking_pace
    }

@app.post("/admin/settings/voice")
def update_voice_settings(
    request: VoiceSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update voice settings"""
    settings = db.query(VoiceSetting).first()
    if not settings:
        settings = VoiceSetting()
        db.add(settings)

    if request.voice_name:
        settings.voice_name = request.voice_name
    if request.greeting_script:
        settings.greeting_script = request.greeting_script
    if request.personality_tone:
        settings.personality_tone = request.personality_tone
    if request.speaking_pace:
        settings.speaking_pace = request.speaking_pace

    db.commit()
    return {"message": "Voice settings updated"}

# ============================================
# ADMIN: FAQ MANAGEMENT
# ============================================

@app.get("/admin/faqs")
def get_faqs(
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get FAQs (public, used by voice agent)"""
    query = db.query(FAQ).filter(FAQ.is_active == True)
    if category:
        query = query.filter(FAQ.category == category)

    faqs = query.order_by(FAQ.priority.desc(), FAQ.created_at).all()
    return {
        "faqs": [
            {
                "id": str(f.id),
                "question": f.question,
                "answer": f.answer,
                "category": f.category,
                "priority": f.priority
            }
            for f in faqs
        ]
    }

@app.post("/admin/faqs")
def create_faq(
    request: FAQCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create FAQ"""
    faq = FAQ(
        question=request.question,
        answer=request.answer,
        category=request.category,
        priority=request.priority
    )
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return {"id": str(faq.id), "message": "FAQ created"}

@app.patch("/admin/faqs/{faq_id}")
def update_faq(
    faq_id: str,
    request: FAQUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update FAQ"""
    faq = db.query(FAQ).filter(FAQ.id == uuid.UUID(faq_id)).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    if request.question:
        faq.question = request.question
    if request.answer:
        faq.answer = request.answer
    if request.category:
        faq.category = request.category
    if request.is_active is not None:
        faq.is_active = request.is_active
    if request.priority is not None:
        faq.priority = request.priority

    db.commit()
    return {"message": "FAQ updated"}

@app.delete("/admin/faqs/{faq_id}")
def delete_faq(
    faq_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete FAQ"""
    faq = db.query(FAQ).filter(FAQ.id == uuid.UUID(faq_id)).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    db.delete(faq)
    db.commit()
    return {"message": "FAQ deleted"}

# ============================================
# ADMIN: BUSINESS INFO
# ============================================

@app.get("/admin/business-info")
def get_business_info(
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get business info"""
    query = db.query(BusinessInfo)
    if category:
        query = query.filter(BusinessInfo.category == category)

    info = query.all()
    return {
        "business_info": [
            {
                "id": str(i.id),
                "key": i.info_key,
                "value": i.info_value,
                "category": i.category
            }
            for i in info
        ]
    }

@app.post("/admin/business-info/{info_key}")
def update_business_info(
    info_key: str,
    request: BusinessInfoUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update business info"""
    info = db.query(BusinessInfo).filter(BusinessInfo.info_key == info_key).first()
    if info:
        info.info_value = request.info_value
    else:
        info = BusinessInfo(info_key=info_key, info_value=request.info_value)
        db.add(info)
    db.commit()
    return {"message": "Business info updated"}

# ============================================
# HEALTH CHECK
# ============================================

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "nudesignink-api", "version": "1.0.0"}

# ============================================
# RUN
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
