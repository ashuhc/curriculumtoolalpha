# Curriculum Generator — Project Outline

## Goal

Take user (teacher) preferences regarding what classes they want to teach, when they want to teach it, how many courses they want to teach etc, and combine that with a set of courses (determined by past enrollment data) — including which courses should be taught, when they should be taught, class size, and how many sections of each course should be created — to generate a final master **undergraduate** curriculum.

---

## Course References

For now, use Coursicle for course reference.

Courses: [catalog.northeastern.edu/course-descriptions/econ](https://catalog.northeastern.edu/course-descriptions/econ/) — no 5000-level courses or beyond.

- If a student is a transfer: "Economics at Northeastern" is a required course.
- **Core courses (must be offered):**
  - Economics at Northeastern
  - 3 Principles courses (Macroeconomics, Microeconomics, and Statistics) → large sections, since these satisfy both Business School and Econ requirements
  - 3 Follow-up courses (Microtheory, Macrotheory, Econometrics)
  - Capstones (2 different)
  - Electives (niche, e.g. Law and Economics) → electives are offered based on whether a professor wants to teach it
  or not. if they do not, the elective is not offered. 
  - Remote sections are capped at 25 students
  - Example section sizes: 40, 43, 45 for smaller classes; 100 - 200 for larger ones (give or take)

### Prerequisite structure by course level

| Level | Prerequisite requirement |
|---|---|
| 1000-level | No prerequisites required |
| 3000-level | Requires principles courses |
| 4000-level | Requires multiple prerequisites and theory courses |

---

## Teacher Preferences

Form: [Teacher Preferences Google Form](https://docs.google.com/forms/d/e/1FAIpQLSd34IzMXlqHeXYR1gOpTrREAJk7N09mC0bM1jTtm4ONfS8lrQ/formResponse?pli=1)
- Contents of the form:
    - Asks faculty for email, name, and which principles courses they would prefer to teach
    - Asks faculty to rank top 6 undergraduate courses they'd like to teach (also helps determine what electives are offered) and attaches a [Undergraduate Program Catalog](https://catalog.northeastern.edu/undergraduate/social-sciences-humanities/economics/#coursestext) for reference. Make sure the faculty also includes the course name and code in response
    - Asks faculty how many courses they'd like to teach per semester (Fall, Spring, Summer 1, Summer 2) NOTE: for ALPHA version, no need to include summers 1 and 2 
    - Asks faculty if they'd like to include a course overload (4th course) for extra compensation
    - Asks faculty for any unique circumstances they'd like to address (ex. joint teaching appointment, a contractual reduction in teaching, a course buyout, or planned sabbatical leave) that may affect teaching

- Check how many times a professor has previously taught each course.
- Courses offered depend on faculty preferences, but core courses must still be covered.
- Diversify course offerings and time slots — also account for what times/courses students want to attend.

### Faculty groups (teaching load requirements)

| Faculty group | Load |
|---|---|
| Tenured faculty | 3 courses/year (though they may teach fewer) |
| Teaching faculty (full-time) | 6 courses/year (some teach extra for additional pay) |
| Temporary faculty | 6 courses/year |
| Adjuncts | 1–2 courses/year |

---

## Scope: Where the Code Starts and Ends

### Inputs (starting point)
- **Course catalog data** — course list, level (1000/3000/4000), prerequisites, and whether it's a core/elective/capstone course (from Coursicle / catalog.northeastern.edu for now)
- **Past enrollment data** — historical class sizes and demand per course, used to estimate how many sections of each course are needed and their size
- **Teacher preferences** — submitted via the Google Form (which courses/times a professor wants to teach)
- **Faculty roster with type** — tenured, full-time teaching faculty, temporary faculty, or adjunct, since this determines each professor's course-load requirement
- **Section size constraints** — e.g., 25-person cap for remote sections, and general size ranges (40–45 for smaller classes, up to 200 for large ones)

### Processing (what the code actually does)
1. Load and validate course catalog + prerequisite rules
2. Load past enrollment data to estimate demand per course
3. Load teacher preference form responses
4. Match teacher preferences against required core courses and each faculty member's course-load requirement
5. Assign course sections (how many sections, what size) based on estimated demand
6. Assign times/slots, aiming to diversify offerings and avoid excessive overlap
7. Flag conflicts (e.g., a core course no one wants to teach, or a faculty member under/over their required load)

### Outputs (ending point)
- A finalized **master undergraduate curriculum** for the semester, including:
  - Which courses are offered
  - Number of sections per course
  - Section size for each
  - Assigned time slot for each section
  - Assigned instructor for each section
- A list of **unresolved conflicts** that need manual review (e.g., no professor available for a required core course)

### Out of scope (for now)
- Graduate-level courses (5000+) are explicitly excluded
- Cross-department scheduling conflicts (e.g., conflicts with non-Econ courses a student might also be taking)
- Room/building assignment (this outline only covers *what* and *when*, not physical location)
- Real-time updates if a professor's preferences change after the initial form submission

---

## Open Questions / Notes to Resolve

- Is "Economics at Northeastern" meant to be the *same* requirement listed under both "transfer students" and "core courses," or are these two separate requirements?
- Confirm whether "3 principles... super large sections to satisfy business school demands AND econ" means these large sections serve both the Business School's and the Econ department's needs simultaneously.
- How should the code resolve a conflict where a required core course has no willing/available instructor? (Manual override, or an automated fallback assignment?)
- Should room/building assignment be added to a later phase, or is that explicitly someone else's responsibility?
- Is there a cutoff date after which teacher preference form responses are no longer accepted/updated for a given semester's run?

