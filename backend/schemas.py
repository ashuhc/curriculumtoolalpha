"""Pydantic request/response schemas. (Optional[...] rather than `X | None` for Python 3.9.)"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator
from typing_extensions import Annotated

SemesterChoice = Literal["None", "Fall", "Spring", "Both"]
TENURED = "Tenured Track / Tenured"
# Older clients/databases may still send "Tenured"; accept it as the renamed group.
FacultyTypeName = Annotated[
    Literal["Tenured Track / Tenured", "Full-Time Teaching", "Temporary", "Adjunct", "Recitation Leader"],
    BeforeValidator(lambda v: TENURED if v == "Tenured" else v),
]


# ---------------------------------------------------------------- planning ---
class PlanSettings(BaseModel):
    """Mirrors engine.Settings; every field has the prototype's default."""
    target_term: str = "Spring 2027"
    growth_multiplier: float = Field(1.0, ge=0.5, le=2.0)
    history_window: int = Field(3, ge=1, le=8)
    apply_trend: bool = True
    max_annual_trend: float = Field(0.10, ge=0, le=0.5)
    large_lecture_cap: int = Field(200, ge=100, le=400)
    small_section_cap: int = Field(45, ge=20, le=80)
    virtual_cap: int = Field(25, ge=5, le=25)       # remote sections are capped at 25
    recitation_cap: int = Field(30, ge=10, le=60)
    min_elective_demand: int = Field(15, ge=0, le=60)
    default_elective_demand: int = Field(40, ge=5, le=100)
    history_fallback: bool = True
    force_fill_core: bool = False
    recitation_leader_load: int = Field(5, ge=1, le=12)

    @field_validator("target_term")
    @classmethod
    def _term(cls, v: str) -> str:
        import re
        m = re.fullmatch(r"\s*(fall|spring)\s+(\d{4})\s*", v, flags=re.IGNORECASE)
        if not m:
            raise ValueError("target_term must look like 'Fall 2027' or 'Spring 2028'")
        return f"{m.group(1).title()} {m.group(2)}"


class PlanRequest(BaseModel):
    settings: PlanSettings = PlanSettings()


class OverrideIn(BaseModel):
    term: str
    section_id: str
    instructor: Optional[str] = None
    sequence: Optional[str] = None


class ManualSectionIn(BaseModel):
    """A hand-added section. Remote sections are asynchronous and capped at 25."""
    term: str
    code: int = Field(..., ge=1000, le=4999, description="Undergraduate only")
    section_no: int = Field(..., ge=1, le=99)
    title: str = Field("", max_length=200)
    instructor: Optional[str] = None                 # roster name; None/"" = unstaffed
    modality: Literal["In-Person", "Remote"] = "In-Person"
    sequence: Optional[str] = None                   # lecture block (1–5, A–H); ignored for remote
    cap: int = Field(..., ge=1, le=300)
    settings: Optional["PlanSettings"] = None        # current plan, to check for ID collisions


class SuggestSectionIn(BaseModel):
    """Ask for conflict-free lecture blocks (and likely volunteers) for one extra section."""
    settings: PlanSettings = PlanSettings()
    code: int = Field(..., ge=1000, le=4999)
    instructor: Optional[str] = None
    exclude_section_id: Optional[str] = None     # the manual section being edited, if any


class ManualSectionOut(BaseModel):
    id: int
    term: str
    section_id: str
    code: int
    section_no: int
    title: str
    instructor: Optional[str]
    modality: str
    sequence: Optional[str]
    cap: int
    created_by: str


class OverrideOut(OverrideIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    updated_at: datetime


# ------------------------------------------------------------------ catalog ---
class CourseIn(BaseModel):
    code: int = Field(..., ge=1000, le=4999, description="Undergraduate only (no 5000+)")
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    active: bool = True


class CourseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    active: Optional[bool] = None


class CourseOut(CourseIn):
    model_config = ConfigDict(from_attributes=True)
    label: str = ""
    level: int = 0
    category: str = ""
    prerequisites: str = ""
    times_offered: int = 0


# ------------------------------------------------------------------ faculty ---
class FacultyIn(BaseModel):
    name: str = Field(..., min_length=3, max_length=120, description="'Last, First'")
    email: str = ""
    faculty_type: Optional[FacultyTypeName] = None
    fall_courseload: Optional[int] = Field(None, ge=0, le=6)
    spring_courseload: Optional[int] = Field(None, ge=0, le=6)
    active: bool = True


class FacultyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=120)
    email: Optional[str] = None
    faculty_type: Optional[FacultyTypeName] = None
    clear_type: bool = False                     # revert to history-inferred group
    # Courses per semester; send null to clear (falls back to the form, then history)
    fall_courseload: Optional[int] = Field(None, ge=0, le=6)
    spring_courseload: Optional[int] = Field(None, ge=0, le=6)
    active: Optional[bool] = None
    overloading: Optional[bool] = None
    overload_semester: Optional[SemesterChoice] = None


class FacultyOut(BaseModel):
    id: int
    name: str
    email: str
    active: bool
    faculty_type: str                 # effective group (confirmed or inferred)
    type_source: str                  # "Confirmed" / "Inferred from history"
    annual_reduction: int             # history-inferred (graduate teaching); informational
    fall_courseload: Optional[int] = None     # scheduler-set; None = not set
    spring_courseload: Optional[int] = None
    # Baseline (seeded) overload approval, and which fields differ from the baseline
    default_overloading: bool = False
    default_overload_semester: str = "None"
    customized: List[str] = []        # e.g. ["Faculty Group", "Fall Courseload", "Approved Overload"]
    overloading: bool
    overload_semester: str
    ug_lectures_per_year: float = 0
    grad_sections_per_year: float = 0
    submissions: int = 0


# -------------------------------------------------------------- preferences ---
class PreferenceIn(BaseModel):
    faculty_id: int
    email: str = Field(..., min_length=3, max_length=200)
    principles: List[int] = []
    ranks: List[int] = Field(default_factory=list, max_length=6)
    fall_target: int = Field(2, ge=0, le=6)
    spring_target: int = Field(2, ge=0, le=6)
    overload: bool = False
    overload_semester: SemesterChoice = "None"
    unique_circumstances: str = Field("", max_length=4000)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("principles")
    @classmethod
    def _principles(cls, v: List[int]) -> List[int]:
        bad = [c for c in v if c not in (1115, 1116)]
        if bad:
            raise ValueError("Principles preferences may only include ECON 1115 and ECON 1116")
        return sorted(set(v))

    @field_validator("ranks")
    @classmethod
    def _ranks(cls, v: List[int]) -> List[int]:
        if any(c >= 5000 for c in v):
            raise ValueError("Graduate (5000+) courses cannot be ranked — undergraduate only")
        if len(set(v)) != len(v):
            raise ValueError("Each ranked course must be different")
        return v


class PreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    faculty_id: int
    faculty_name: str
    submitted_at: datetime
    email: str
    principles: List[int]
    ranks: List[int]
    fall_target: int
    spring_target: int
    overload: bool
    overload_semester: str
    unique_circumstances: str
    submitted_by: Optional[str] = None


# -------------------------------------------------------------------- auth ---
class LoginIn(BaseModel):
    email: str
    password: str


class UserIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    name: str = Field(..., min_length=2, max_length=120)
    role: Literal["admin", "faculty"] = "faculty"
    password: str = Field(..., min_length=8, max_length=200)
    faculty_id: Optional[int] = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v:
            raise ValueError("Enter a valid email address")
        return v


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    role: Optional[Literal["admin", "faculty"]] = None
    password: Optional[str] = Field(None, min_length=8, max_length=200)
    faculty_id: Optional[int] = None
    unlink_faculty: bool = False
    active: Optional[bool] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=200)


# ------------------------------------------------------------ collaboration ---
class LockIn(BaseModel):
    term: str
    section_id: str


class CommentIn(BaseModel):
    term: str
    section_id: str
    body: str = Field(..., min_length=1, max_length=4000)
    parent_id: Optional[int] = None


class CommentUpdate(BaseModel):
    resolved: Optional[bool] = None
    body: Optional[str] = Field(None, min_length=1, max_length=4000)


class PublishIn(BaseModel):
    settings: PlanSettings = PlanSettings()
    note: str = Field("", max_length=2000)
    allow_critical: bool = False
