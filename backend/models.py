"""SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Course(Base):
    """Undergraduate catalog entry (5000+ graduate courses are rejected at the API)."""
    __tablename__ = "courses"

    code: Mapped[int] = mapped_column(Integer, primary_key=True)          # e.g. 3424
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Faculty(Base):
    __tablename__ = "faculty"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)   # "Last, First"
    email: Mapped[str] = mapped_column(String(200), default="")
    # None => group is inferred from teaching history until an admin confirms it
    faculty_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    annual_reduction: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # legacy; no longer edited
    # Courses per semester set by a scheduler; None => preference form, then teaching history
    fall_courseload: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    spring_courseload: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    overload: Mapped[Optional["Overload"]] = relationship(
        back_populates="faculty", uselist=False, cascade="all, delete-orphan")
    submissions: Mapped[List["PreferenceSubmission"]] = relationship(
        back_populates="faculty", cascade="all, delete-orphan")


class Overload(Base):
    """Admin-approved course overloads (replaces faculty_overloads.json)."""
    __tablename__ = "overloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), unique=True)
    overloading: Mapped[bool] = mapped_column(Boolean, default=False)
    semester: Mapped[str] = mapped_column(String(10), default="None")      # None / Fall / Spring / Both

    faculty: Mapped[Faculty] = relationship(back_populates="overload")


class PreferenceSubmission(Base):
    """One faculty teaching-preference form response (replaces teacher_preferences.csv)."""
    __tablename__ = "preference_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    email: Mapped[str] = mapped_column(String(200), default="")
    principles: Mapped[list] = mapped_column(JSON, default=list)          # [1115, 1116]
    ranks: Mapped[list] = mapped_column(JSON, default=list)               # up to 6 course codes, in order
    fall_target: Mapped[int] = mapped_column(Integer, default=2)
    spring_target: Mapped[int] = mapped_column(Integer, default=2)
    overload: Mapped[bool] = mapped_column(Boolean, default=False)
    overload_semester: Mapped[str] = mapped_column(String(10), default="None")
    unique_circumstances: Mapped[str] = mapped_column(Text, default="")
    # Who actually submitted it ("Name <email>"), so on-behalf submissions are auditable
    submitted_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    faculty: Mapped[Faculty] = relationship(back_populates="submissions")


class EnrollmentRecord(Base):
    """Historical section-level enrollment (mirrors ECON_Enrollment.xlsx columns)."""
    __tablename__ = "enrollment_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_period: Mapped[str] = mapped_column(String(60), index=True)
    campus: Mapped[str] = mapped_column(String(20), default="")
    course_number: Mapped[int] = mapped_column(Integer, index=True)
    course_title: Mapped[str] = mapped_column(String(200), default="")
    crn: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    instructional_method: Mapped[str] = mapped_column(String(40), default="")
    instructor: Mapped[str] = mapped_column(String(120), default="")
    schedule: Mapped[str] = mapped_column(String(80), default="")
    maximum_enrollment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ug_enrollment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class ManualSection(Base):
    """A section a scheduler added by hand (e.g. an elective the solver didn't offer) for one term."""
    __tablename__ = "manual_sections"
    __table_args__ = (UniqueConstraint("term", "section_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(20), index=True)
    section_id: Mapped[str] = mapped_column(String(30))                    # "ECON 3424-02"
    code: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(4))                        # "02"
    title: Mapped[str] = mapped_column(String(200))
    instructor: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)   # None = unstaffed
    virtual: Mapped[bool] = mapped_column(Boolean, default=False)
    sequence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)      # lecture block; None = unscheduled
    cap: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScheduleOverride(Base):
    """Manual instructor / sequence edit to a generated section for one term."""
    __tablename__ = "schedule_overrides"
    __table_args__ = (UniqueConstraint("term", "section_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(20), index=True)             # "Spring 2027"
    section_id: Mapped[str] = mapped_column(String(30))                    # "ECON 2315-03"
    instructor: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    sequence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ==============================================================================
# Collaboration & access control
# ==============================================================================
class User(Base):
    """Signed-in account. role = "admin" (scheduler) or "faculty"."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="faculty")
    password_hash: Mapped[str] = mapped_column(String(200))
    faculty_id: Mapped[Optional[int]] = mapped_column(ForeignKey("faculty.id", ondelete="SET NULL"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    faculty: Mapped[Optional[Faculty]] = relationship()


class SectionLock(Base):
    """An admin's temporary edit lock on one section (expires automatically)."""
    __tablename__ = "section_locks"
    __table_args__ = (UniqueConstraint("term", "section_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(20), index=True)
    section_id: Mapped[str] = mapped_column(String(30))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user_name: Mapped[str] = mapped_column(String(120))
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class SectionComment(Base):
    """Threaded discussion on a section (parent_id = reply-to)."""
    __tablename__ = "section_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(20), index=True)
    section_id: Mapped[str] = mapped_column(String(30), index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("section_comments.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_name: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Publication(Base):
    """Immutable snapshot of a finalized master schedule (for catalog import)."""
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    published_by: Mapped[str] = mapped_column(String(120))
    note: Mapped[str] = mapped_column(Text, default="")
    settings: Mapped[dict] = mapped_column(JSON)
    sections: Mapped[list] = mapped_column(JSON)          # master rows (snake_case keys)
    critical: Mapped[int] = mapped_column(Integer, default=0)
    warning: Mapped[int] = mapped_column(Integer, default=0)
