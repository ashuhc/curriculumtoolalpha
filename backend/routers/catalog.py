"""Course catalog and faculty roster (incl. approved overloads)."""
from __future__ import annotations

from typing import List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import engine as eng
import services as svc
from auth import require_admin
from database import get_db
from models import Course, Faculty, Overload, User
from schemas import CourseIn, CourseOut, CourseUpdate, FacultyIn, FacultyOut, FacultyUpdate

router = APIRouter(prefix="/api", tags=["catalog"])


# ------------------------------------------------------------------ courses ---
def _course_out(c: Course, offered: dict) -> CourseOut:
    return CourseOut(code=c.code, title=c.title, description=c.description or "", active=c.active,
                     label=f"ECON {c.code} - {c.title}", level=eng.course_level(c.code),
                     category=eng.course_category(c.code),
                     prerequisites=eng.format_prereqs(eng.get_prerequisites(c.code)),
                     times_offered=int(offered.get(c.code, 0)))


@router.get("/courses", response_model=List[CourseOut])
def list_courses(include_inactive: bool = False, db: Session = Depends(get_db)):
    q = db.query(Course).filter(Course.code < 5000)
    if not include_inactive:
        q = q.filter(Course.active.is_(True))
    enr = svc.clean_enrollment(db)
    offered = enr.groupby("course")["term"].nunique().to_dict() if not enr.empty else {}
    return [_course_out(c, offered) for c in q.order_by(Course.code).all()]


@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(body: CourseIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.get(Course, body.code):
        raise HTTPException(409, f"ECON {body.code} already exists")
    c = Course(**body.model_dump())
    db.add(c)
    db.commit()
    svc.bump_version("courses")
    return _course_out(c, {})


@router.put("/courses/{code}", response_model=CourseOut)
def update_course(code: int, body: CourseUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = db.get(Course, code)
    if not c:
        raise HTTPException(404, "Course not found")
    if body.active is False and (code in eng.MANDATORY_CORE or code in eng.RECITATION_FOR):
        raise HTTPException(400, "Mandatory core courses cannot be deactivated")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    db.commit()
    svc.bump_version("courses")
    return _course_out(c, {})


@router.delete("/courses/{code}", status_code=204)
def delete_course(code: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = db.get(Course, code)
    if not c:
        raise HTTPException(404, "Course not found")
    if code in eng.MANDATORY_CORE or code in eng.RECITATION_FOR:
        raise HTTPException(400, "Mandatory core courses cannot be deleted")
    db.delete(c)
    db.commit()
    svc.bump_version("courses")


# ------------------------------------------------------------------ faculty ---
def faculty_out(db: Session, include_inactive=True) -> List[FacultyOut]:
    q = db.query(Faculty)
    if not include_inactive:
        q = q.filter(Faculty.active.is_(True))
    faculty = q.order_by(Faculty.name).all()
    roster = svc.inferred_roster(db, faculty).set_index("Faculty") if faculty else pd.DataFrame()
    out = []
    for f in faculty:
        r = roster.loc[f.name] if f.name in roster.index else None
        out.append(FacultyOut(
            id=f.id, name=f.name, email=f.email or "", active=f.active,
            faculty_type=eng.normalize_faculty_type(f.faculty_type or (r["Type"] if r is not None else "Adjunct")),
            type_source="Confirmed" if f.faculty_type else "Inferred from history",
            annual_reduction=int(r["Annual Reduction"]) if r is not None else 0,
            fall_courseload=f.fall_courseload, spring_courseload=f.spring_courseload,
            overloading=bool(f.overload and f.overload.overloading),
            overload_semester=f.overload.semester if f.overload else "None",
            default_overloading=svc.baseline_overload_for(f.name)[0],
            default_overload_semester=svc.baseline_overload_for(f.name)[1],
            customized=svc.customized_fields(f),
            ug_lectures_per_year=float(r["UG Lectures / Yr (hist.)"]) if r is not None else 0.0,
            grad_sections_per_year=float(r["Grad Sections / Yr (hist.)"]) if r is not None else 0.0,
            submissions=len(f.submissions),
        ))
    return out


@router.get("/faculty", response_model=List[FacultyOut])
def list_faculty(include_inactive: bool = False, db: Session = Depends(get_db)):
    return faculty_out(db, include_inactive)


@router.post("/faculty", response_model=FacultyOut, status_code=201)
def create_faculty(body: FacultyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    name = body.name.strip()
    if db.query(Faculty).filter(Faculty.name == name).first():
        raise HTTPException(409, f"{name} already exists")
    db.add(Faculty(**{**body.model_dump(), "name": name}))
    db.commit()
    svc.bump_version("faculty")
    return next(f for f in faculty_out(db) if f.name == name)


@router.put("/faculty/{fid}", response_model=FacultyOut)
def update_faculty(fid: int, body: FacultyUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    f = db.get(Faculty, fid)
    if not f:
        raise HTTPException(404, "Faculty not found")
    data = body.model_dump(exclude_none=True)
    sent = body.model_dump(exclude_unset=True)
    if data.pop("clear_type", False):
        f.faculty_type, f.annual_reduction = None, None
    for k in ("name", "email", "faculty_type", "active"):
        if k in data:
            setattr(f, k, data[k].strip() if isinstance(data[k], str) else data[k])
    for k in ("fall_courseload", "spring_courseload"):
        if k in sent:                                   # explicit null clears the value
            setattr(f, k, sent[k])
    if "overloading" in data or "overload_semester" in data:
        if not f.overload:
            f.overload = Overload(overloading=False, semester="None")
        if "overloading" in data:
            f.overload.overloading = data["overloading"]
        if "overload_semester" in data:
            f.overload.semester = data["overload_semester"]
        if not f.overload.overloading:
            f.overload.semester = "None"
        elif f.overload.semester == "None":
            f.overload.semester = "Both"
    db.commit()
    svc.bump_version("faculty")
    return next(o for o in faculty_out(db) if o.id == fid)


@router.post("/faculty/reset")
def reset_all_faculty(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Restore every customized row to its inferred group, automatic courseloads and seeded overload."""
    names = [f.name for f in db.query(Faculty).all() if svc.reset_faculty_to_default(f)]
    db.commit()
    if names:
        svc.bump_version("faculty")
    return {"reset": len(names), "faculty": names}


@router.post("/faculty/{fid}/reset", response_model=FacultyOut)
def reset_faculty(fid: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Restore one row to its inferred group, automatic courseloads and seeded overload."""
    f = db.get(Faculty, fid)
    if not f:
        raise HTTPException(404, "Faculty not found")
    svc.reset_faculty_to_default(f)
    db.commit()
    svc.bump_version("faculty")
    return next(o for o in faculty_out(db) if o.id == fid)


@router.delete("/faculty/{fid}", status_code=204)
def delete_faculty(fid: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    f = db.get(Faculty, fid)
    if not f:
        raise HTTPException(404, "Faculty not found")
    db.delete(f)
    db.commit()
    svc.bump_version("faculty")
