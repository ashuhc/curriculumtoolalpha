"""End-to-end API tests (run: `pytest` from /backend)."""
TERM = "Spring 2027"
S = {"settings": {"target_term": TERM}}


def test_health_and_meta(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["enrollment_records"] > 800 and h["faculty"] == 52
    m = client.get("/api/meta").json()
    assert TERM in m["terms"]["upcoming"]
    assert len(m["sequences"]["class"]) == 13 and len(m["sequences"]["lab"]) == 11


def test_auth_roles(client, admin, faculty):
    assert client.post("/api/auth/login", json={"email": "admin@northeastern.edu", "password": "nope"}).status_code == 401
    assert client.get("/api/auth/me", headers=faculty).json()["role"] == "faculty"
    assert client.get("/api/users", headers=faculty).status_code == 403
    assert client.get("/api/users").status_code == 401
    assert len(client.get("/api/users", headers=admin).json()) == 3


def test_courses_are_undergraduate_only(client, admin):
    assert all(c["code"] < 5000 for c in client.get("/api/courses").json())
    assert client.post("/api/courses", json={"code": 5300, "title": "Grad"}, headers=admin).status_code == 422
    assert client.delete("/api/courses/1115", headers=admin).status_code == 400


def test_demand(client):
    d = client.post("/api/plan/demand", json=S).json()
    rec = {r["code"]: r for r in d["demand"] if r["category"] == "Recitation"}
    # Only students seated in large (200-seat) lectures need recitations; 45-seat sections don't
    for lecture, rec_code in ((1115, 1125), (1116, 1126)):
        row = next(r for r in d["demand"] if r["code"] == lecture and not r["virtual"])
        caps = [int(c) for c in row["section_caps"].split(", ")]
        large = sum(min(c, round(row["projected_enrollment"] * c / sum(caps))) for c in caps if c == 200)
        assert rec[rec_code]["planned_sections"] == -(-large // 30)  # ceil(large-lecture students / 30)
    # Spring 2027 ECON 1116 mixes 200-seat lectures with small sections: the small ones add no recitations
    row = next(r for r in d["demand"] if r["code"] == 1116 and not r["virtual"])
    assert any(int(c) < 100 for c in row["section_caps"].split(", "))
    assert rec[1126]["planned_sections"] < -(-row["projected_enrollment"] // 30)
    assert all(int(c) <= 25 for r in d["demand"] if r["virtual"] for c in r["section_caps"].split(", "))


def test_schedule_core_staffed_and_no_recitation_overlap(client):
    s = client.post("/api/plan/schedule", json=S).json()
    assert s["summary"]["core_staffed"] == s["summary"]["core_sections"]
    assert not any(c["category"] in ("Recitation overlaps lecture", "Instructor time overlap") for c in s["conflicts"])
    caps = {r["section_id"]: r["section_cap"] for r in s["master"]}
    recs = [r for r in s["master"] if r["component"] == "Recitation"]
    assert recs and all(caps[r["linked_lecture"]] == 200 for r in recs)   # never tied to a small section


def test_preference_submissions_and_on_behalf_audit(client, faculty):
    me = client.get("/api/auth/me", headers=faculty).json()
    body = {"faculty_id": me["faculty_id"], "email": "m.stone@northeastern.edu", "ranks": [3424, 1116],
            "principles": [1116], "fall_target": 3, "spring_target": 3}
    assert client.post("/api/preferences", json=body, headers=faculty).status_code == 201
    # Submitting on behalf of another instructor is allowed and records who submitted it
    other = client.post("/api/preferences", json={**body, "faculty_id": me["faculty_id"] + 1}, headers=faculty)
    assert other.status_code == 201 and other.json()["submitted_by"] == f"{me['name']} <{me['email']}>"
    assert other.json()["faculty_id"] != me["faculty_id"]
    assert client.post("/api/preferences", json={**body, "ranks": [5200]}, headers=faculty).status_code == 422
    assert client.post("/api/preferences", json=body).status_code == 401


def test_locks_block_other_schedulers(client, admin, admin2, faculty):
    sid = client.post("/api/plan/schedule", json=S).json()["master"][1]["section_id"]
    assert client.post("/api/locks", json={"term": TERM, "section_id": sid}, headers=faculty).status_code == 403
    assert client.post("/api/locks", json={"term": TERM, "section_id": sid}, headers=admin).status_code == 200
    assert client.post("/api/locks", json={"term": TERM, "section_id": sid}, headers=admin2).status_code == 409
    edit = {"term": TERM, "section_id": sid, "sequence": "1"}
    assert client.put("/api/plan/overrides", json=edit, headers=admin2).status_code == 423
    assert client.put("/api/plan/overrides", json=edit, headers=admin).status_code == 200
    s = client.post("/api/plan/schedule", json=S).json()
    assert sid in s["overridden"] and any(lk["section_id"] == sid for lk in s["locks"])
    client.delete(f"/api/locks?term={TERM.replace(' ', '%20')}&section_id={sid}", headers=admin)
    assert client.put("/api/plan/overrides", json={**edit, "sequence": None}, headers=admin2).status_code == 200


def test_threaded_comments(client, admin, faculty):
    root = client.post("/api/comments", json={"term": TERM, "section_id": "ECON 2315-01", "body": "Room too small?"},
                       headers=faculty).json()
    reply = client.post("/api/comments", json={"term": TERM, "section_id": "ECON 2315-01", "body": "Moving it.",
                                               "parent_id": root["id"]}, headers=admin)
    assert reply.status_code == 201 and reply.json()["parent_id"] == root["id"]
    assert client.post("/api/comments", json={"term": TERM, "section_id": "X", "body": "anon"}).status_code == 401
    counts = client.post("/api/plan/schedule", json=S).json()["comment_counts"]
    assert counts.get("ECON 2315-01") == 2
    assert client.patch(f"/api/comments/{root['id']}", json={"resolved": True}, headers=admin).json()["resolved"]


def test_publish_and_catalog_export(client, admin, faculty):
    assert client.post("/api/publications", json=S, headers=faculty).status_code == 403
    pub = client.post("/api/publications", json={**S, "note": "v1"}, headers=admin)
    assert pub.status_code == 201, pub.text
    csv = client.get(f"/api/publications/{pub.json()['id']}/export")
    header = csv.text.splitlines()[0]
    assert "Course Number" in header and "Start Time" in header
    assert client.post("/api/publications", json=S, headers=admin).json()["version"] == 2


def test_websocket_broadcasts_edits(client, admin):
    token = admin["Authorization"].split()[1]
    with client.websocket_connect(f"/ws?token={token}") as ws:
        assert ws.receive_json()["type"] == "presence"
        client.post("/api/comments", json={"term": TERM, "section_id": "ECON 1000-01", "body": "hi"}, headers=admin)
        for _ in range(5):
            msg = ws.receive_json()
            if msg["type"] == "comment":
                assert msg["comment"]["body"] == "hi"
                break
        else:
            raise AssertionError("no comment event received")


def test_require_login_gates_everything(client, admin, monkeypatch):
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setenv("REQUIRE_LOGIN", "true")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/meta").json()["require_login"] is True
    assert client.get("/api/courses").status_code == 401
    assert client.post("/api/plan/schedule", json=S).status_code == 401
    assert client.get("/api/courses", headers=admin).status_code == 200
    try:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
        raise AssertionError("anonymous websocket should be refused")
    except WebSocketDisconnect:
        pass


def test_faculty_group_rename_and_courseloads(client, admin):
    assert "Tenured Track / Tenured" in client.get("/api/meta").json()["faculty_types"]
    f = client.get("/api/faculty").json()[0]
    # Legacy label is accepted and stored under the new name
    r = client.put(f"/api/faculty/{f['id']}", json={"faculty_type": "Tenured"}, headers=admin).json()
    assert r["faculty_type"] == "Tenured Track / Tenured" and r["type_source"] == "Confirmed"
    r = client.put(f"/api/faculty/{f['id']}", json={"fall_courseload": 1, "spring_courseload": 2}, headers=admin).json()
    assert (r["fall_courseload"], r["spring_courseload"]) == (1, 2)
    wl = {w["faculty"]: w for w in client.post("/api/plan/schedule", json=S).json()["workload"]}
    assert wl[f["name"]]["term_target"] == 2 and wl[f["name"]]["target_source"] == "Scheduler courseload"
    assert wl[f["name"]]["other_semester_planned"] == 1
    # null clears one semester without touching the other
    r = client.put(f"/api/faculty/{f['id']}", json={"spring_courseload": None}, headers=admin).json()
    assert (r["fall_courseload"], r["spring_courseload"]) == (1, None)
    assert client.put(f"/api/faculty/{f['id']}", json={"fall_courseload": 9}, headers=admin).status_code == 422
    client.put(f"/api/faculty/{f['id']}", json={"clear_type": True, "fall_courseload": None}, headers=admin)


def test_bulk_revert_skips_sections_locked_by_others(client, admin, admin2):
    sched = client.post("/api/plan/schedule", json=S).json()
    a, b = [r["section_id"] for r in sched["master"] if r["component"] == "Lecture"][:2]
    for sid in (a, b):
        assert client.put("/api/plan/overrides", json={"term": TERM, "section_id": sid, "sequence": "A"}, headers=admin).status_code == 200
    assert client.post("/api/locks", json={"term": TERM, "section_id": b}, headers=admin2).status_code in (200, 201)
    r = client.delete(f"/api/plan/overrides?term={TERM}", headers=admin).json()
    other = client.get("/api/auth/me", headers=admin2).json()["name"]
    assert r["reverted"] == [a] and r["skipped"] == [{"section_id": b, "locked_by": other}]
    client.delete(f"/api/locks?term={TERM}&section_id={b}", headers=admin2)
    r = client.delete(f"/api/plan/overrides?term={TERM}&section_id={b}", headers=admin).json()
    assert r["reverted"] == [b] and client.get(f"/api/plan/overrides?term={TERM}").json() == []


def test_faculty_reset_to_default(client, admin):
    rows = client.get("/api/faculty").json()
    f, g = rows[1], rows[2]
    assert f["customized"] == [] and g["customized"] == []
    client.put(f"/api/faculty/{f['id']}", json={"faculty_type": "Adjunct", "fall_courseload": 2,
                                                  "overloading": not f["default_overloading"]}, headers=admin)
    client.put(f"/api/faculty/{g['id']}", json={"spring_courseload": 1}, headers=admin)
    cur = {x["id"]: x for x in client.get("/api/faculty").json()}
    assert cur[f["id"]]["customized"] == ["Faculty Group", "Fall Courseload", "Approved Overload"]
    assert cur[g["id"]]["customized"] == ["Spring Courseload"]
    one = client.post(f"/api/faculty/{f['id']}/reset", headers=admin).json()
    assert one["customized"] == [] and one["type_source"] != "Confirmed" and one["fall_courseload"] is None
    assert one["overloading"] == f["default_overloading"]
    r = client.post("/api/faculty/reset", headers=admin).json()
    assert g["name"] in r["faculty"]
    assert all(x["customized"] == [] for x in client.get("/api/faculty").json())


def test_half_full_rule_for_additional_sections():
    import engine as eng
    st = eng.Settings(target_term=TERM)
    # 60 students, 45-seat cap: a 2nd section would hold 15 (< 23) -> one 49-seat section, 11 unseated
    assert eng._section_caps_for(3424, False, 60, 45, st) == ([49], 11)
    # 70 students: overflow of 25 fills a 2nd section past half -> two sections
    assert eng._section_caps_for(3424, False, 70, 45, st) == ([45, 45], 0)
    # small overflow is still absorbed by the 10% tolerance
    assert eng._section_caps_for(3424, False, 44, 40, st) == ([44], 0)
    assert eng._section_caps_for(2316, False, 240, 32, st) == ([35] * 7, 0)
    # the first section always runs (electives also need min_elective_demand)
    assert eng._section_caps_for(3424, False, 16, 45, st) == ([45], 0)
    # remote caps are hard: 27 students -> one 25-seat section, 2 unseated
    assert eng._section_caps_for(1115, True, 27, 25, st) == ([25], 2)
    # Principles: 466 -> 2 large lectures; the 66 left fit one 49-seat section, not two 45s
    assert eng._section_caps_for(1116, False, 466, 45, st) == ([200, 200, 49], 17)


def test_demand_over_capacity_is_reported(client):
    s = client.post("/api/plan/schedule", json={"settings": {"target_term": "Fall 2026"}}).json()
    over = [c for c in s["conflicts"] if c["category"] == "Demand over capacity"]
    assert any(c["course_section"] == "ECON 1000" and c["severity"] == "Warning" for c in over)    # core
    assert all(c["severity"] in ("Info", "Warning") for c in over)


def test_manual_sections(client, admin, admin2):
    plan = client.post("/api/plan/schedule", json={"settings": {"target_term": "Fall 2026"}}).json()
    fac = client.get("/api/faculty").json()[3]["name"]
    term, settings = "Fall 2026", {"target_term": "Fall 2026"}
    body = {"term": term, "code": 1000, "section_no": 2, "instructor": fac, "modality": "In-Person",
            "sequence": "B", "cap": 30, "settings": settings}
    taken = next(r for r in plan["master"] if r["course"] == "ECON 1000")["section"]
    assert client.post("/api/plan/sections", json={**body, "section_no": int(taken)}, headers=admin).status_code == 409
    assert client.post("/api/plan/sections", json={**body, "sequence": "L"}, headers=admin).status_code == 422
    assert client.post("/api/plan/sections", json={**body, "modality": "Remote", "cap": 40}, headers=admin).status_code == 422
    assert client.post("/api/plan/sections", json={**body, "code": 1125}, headers=admin).status_code == 422
    assert client.post("/api/plan/sections", json={**body, "instructor": "Nobody, Real"}, headers=admin).status_code == 422
    assert client.post("/api/plan/sections", json=body).status_code == 401
    r = client.post("/api/plan/sections", json=body, headers=admin)
    assert r.status_code == 201 and r.json()["section_id"] == "ECON 1000-02"
    assert client.post("/api/plan/sections", json=body, headers=admin).status_code == 409
    s = client.post("/api/plan/schedule", json={"settings": settings}).json()
    row = next(m for m in s["master"] if m["section_id"] == "ECON 1000-02")
    assert row["instructor"] == fac and row["sequence"] == "B" and row["section_cap"] == 30 and row["match_basis"] == "Manual section"
    group = [m for m in s["master"] if m["course"] == "ECON 1000" and m["modality"] == "In-Person"]
    assert sum(m["projected_enrollment"] for m in group) == 104     # demand re-spread over all seats (89 + 30)
    assert "ECON 1000-02" in s["overridden"] and s["summary"]["overrides_applied"] >= 1
    assert not any(c["category"] == "Demand over capacity" and c["course_section"] == "ECON 1000" for c in s["conflicts"])
    # edit (renumber) then revert via the overrides endpoint
    mid = r.json()["id"]
    u = client.put(f"/api/plan/sections/{mid}", json={**body, "section_no": 7, "cap": 25}, headers=admin)
    assert u.status_code == 200 and u.json()["section_id"] == "ECON 1000-07"
    gone = client.delete(f"/api/plan/overrides?term={term}&section_id=ECON 1000-07", headers=admin).json()
    assert gone["reverted"] == ["ECON 1000-07"]
    s = client.post("/api/plan/schedule", json={"settings": settings}).json()
    assert not any(m["section_id"] == "ECON 1000-07" for m in s["master"]) and s["manual_sections"] == []


def test_suggest_section_avoids_instructor_and_core_conflicts(client, admin):
    import engine as eng
    settings = {"target_term": "Fall 2026"}
    plan = client.post("/api/plan/schedule", json={"settings": settings}).json()
    busy_name = next(r["instructor"] for r in plan["master"]
                     if r["modality"] == "In-Person" and r["sequence"] in eng.CLASS_SEQUENCES and r["instructor"] != eng.UNSTAFFED)
    busy = [r["sequence"] for r in plan["master"] if r["instructor"] == busy_name and r["sequence"] in eng.ALL_SLOTS]
    r = client.post("/api/plan/suggest-section", json={"settings": settings, "code": 1230, "instructor": busy_name}, headers=admin)
    assert r.status_code == 200
    blocks = r.json()["blocks"]
    assert blocks and all(b["sequence"] in eng.CLASS_SEQUENCES for b in blocks)
    assert not any(eng.slots_overlap(b["sequence"], x) for b in blocks for x in busy)    # hard constraint
    assert blocks == sorted(blocks, key=lambda b: (b["cost"], b["sequence"]))
    assert blocks[0]["reasons"][0].startswith(f"No overlap with {busy_name}")
    assert isinstance(r.json()["volunteers"], list)
    assert client.post("/api/plan/suggest-section", json={"settings": settings, "code": 1230}).status_code == 401
    # every over-capacity row is a Warning now
    over = [c for c in plan["conflicts"] if c["category"] == "Demand over capacity"]
    assert over and all(c["severity"] == "Warning" for c in over)


def test_raise_section_cap(client, admin):
    term, settings = "Fall 2026", {"target_term": "Fall 2026"}
    s = client.post("/api/plan/schedule", json={"settings": settings}).json()
    gap = next(g for g in s["capacity_gaps"] if g["code"] == 4997 and not g["virtual"])
    sec = next(m for m in s["master"] if m["course"] == "ECON 4997" and m["component"] == "Lecture")
    old_cap, instr = sec["section_cap"], sec["instructor"]
    # partial raise first: gap shrinks but stays a Warning with updated numbers
    assert client.put("/api/plan/overrides", json={"term": term, "section_id": sec["section_id"], "cap": old_cap + 2}, headers=admin).status_code == 200
    s = client.post("/api/plan/schedule", json={"settings": settings}).json()
    g = next(g for g in s["capacity_gaps"] if g["code"] == 4997)
    assert g["unseated"] == gap["unseated"] - 2 and sec["section_id"] in s["overridden"]
    assert any(c["category"] == "Demand over capacity" and c["course_section"] == "ECON 4997" and f"{g['unseated']} projected" in c["details"]
               for c in s["conflicts"])
    # raise enough to seat everyone: warning cleared, projection re-spread, instructor untouched
    new_cap = old_cap + gap["unseated"]
    client.put("/api/plan/overrides", json={"term": term, "section_id": sec["section_id"], "cap": new_cap}, headers=admin)
    s = client.post("/api/plan/schedule", json={"settings": settings}).json()
    row = next(m for m in s["master"] if m["section_id"] == sec["section_id"])
    assert row["section_cap"] == new_cap and row["projected_enrollment"] == gap["projected"] and row["instructor"] == instr
    assert not any(g["code"] == 4997 for g in s["capacity_gaps"])
    assert not any(c["category"] == "Demand over capacity" and c["course_section"] == "ECON 4997" for c in s["conflicts"])
    # Enrollment Projections reflects the new seats
    d = client.post("/api/plan/demand", json={"settings": settings}).json()
    r = next(x for x in d["demand"] if x["code"] == 4997 and not x["virtual"])
    assert r["section_caps"] == str(new_cap) and r["seats_offered"] == new_cap and abs(r["seat_fill"] - 1.0) < 1e-9
    assert "over capacity" not in r["notes"] and "manual" in r["notes"]
    # a later instructor edit keeps the cap (partial update), and Revert restores the default
    client.put("/api/plan/overrides", json={"term": term, "section_id": sec["section_id"], "sequence": "E"}, headers=admin)
    o = next(o for o in client.get(f"/api/plan/overrides?term={term}").json() if o["section_id"] == sec["section_id"])
    assert o["cap"] == new_cap and o["sequence"] == "E"
    client.delete(f"/api/plan/overrides?term={term}&section_id={sec['section_id']}", headers=admin)
    s = client.post("/api/plan/schedule", json={"settings": settings}).json()
    assert next(m for m in s["master"] if m["section_id"] == sec["section_id"])["section_cap"] == old_cap
    assert any(g["code"] == 4997 for g in s["capacity_gaps"])
    assert client.put("/api/plan/overrides", json={"term": term, "section_id": sec["section_id"], "cap": 0}, headers=admin).status_code == 422


def test_delete_section_undo_redo(client, admin, admin2):
    term, settings = "Fall 2026", {"target_term": "Fall 2026"}
    sched = lambda: client.post("/api/plan/schedule", json={"settings": settings}).json()
    s0 = sched()
    gapped = {(g["code"], g["virtual"]) for g in s0["capacity_gaps"]}
    lectures = [m for m in s0["master"] if m["component"] == "Lecture" and m["modality"] == "In-Person"]
    by_course: dict[str, list] = {}
    for m in lectures:
        by_course.setdefault(m["course"], []).append(m)
    course, group = next((c, g) for c, g in by_course.items()
                         if len(g) >= 2 and (int(c.split()[1]), False) not in gapped
                         and not any(r["linked_lecture"] in {x["section_id"] for x in g} for r in s0["master"]))
    victim = group[-1]["section_id"]
    assert client.delete(f"/api/plan/section?term={term}&section_id={victim}").status_code == 401
    r = client.delete(f"/api/plan/section?term={term}&section_id={victim}", headers=admin)
    assert r.status_code == 200 and r.json()["kind"] == "generated"
    before, after = r.json()["before"], r.json()["after"]
    assert before["override"] is None and after["override"]["removed"] is True
    s1 = sched()
    assert victim not in {m["section_id"] for m in s1["master"]} and len(s1["master"]) == len(s0["master"]) - 1
    assert [x["section_id"] for x in s1["removed_sections"]] == [victim] and victim in s1["overridden"]
    assert victim not in s1["summary"]["overrides_stale"]
    code = int(course.split()[1])
    left = [m for m in s1["master"] if m["course"] == course and m["modality"] == "In-Person" and m["component"] == "Lecture"]
    projected = sum(m["projected_enrollment"] for m in group)
    seats = sum(m["section_cap"] for m in left)
    assert all(m["projected_enrollment"] <= m["section_cap"] for m in left)
    assert sum(m["projected_enrollment"] for m in left) >= min(projected, seats) - len(left)   # re-spread (rounding)
    if projected > seats:      # deletion pushed demand over the remaining seats → Warning with updated counts
        gap = next(g for g in s1["capacity_gaps"] if g["code"] == code and not g["virtual"])
        assert gap["unseated"] == gap["projected"] - seats and gap["removed"] == 1 and gap["sections"] == len(left)
        c = next(c for c in s1["conflicts"] if c["category"] == "Demand over capacity" and c["course_section"] == course)
        assert c["severity"] == "Warning" and "deleted" in c["details"] and s1["summary"]["warning"] > s0["summary"]["warning"]
    # Undo: restore the "before" snapshot, guarded by the "after" snapshot
    body = lambda state, expect: {"term": term, "items": [{"state": state, "expect": expect}]}
    u = client.put("/api/plan/section-state", json=body(before, after), headers=admin)
    assert u.status_code == 200 and u.json()[0]["override"] is None
    s2 = sched()
    assert victim in {m["section_id"] for m in s2["master"]} and s2["removed_sections"] == []
    assert s2["summary"]["warning"] == s0["summary"]["warning"]
    # a stale snapshot is refused instead of overwriting someone else's work
    assert client.put("/api/plan/section-state", json=body(before, after), headers=admin).status_code == 409
    # Redo
    assert client.put("/api/plan/section-state", json=body(after, before), headers=admin).status_code == 200
    assert victim not in {m["section_id"] for m in sched()["master"]}
    # Revert also restores a deleted section
    client.delete(f"/api/plan/overrides?term={term}&section_id={victim}", headers=admin)
    assert victim in {m["section_id"] for m in sched()["master"]}
    # locks: another scheduler can't delete a section someone is editing
    assert client.post("/api/locks", json={"term": term, "section_id": victim}, headers=admin2).status_code in (200, 201)
    assert client.delete(f"/api/plan/section?term={term}&section_id={victim}", headers=admin).status_code == 423
    client.delete(f"/api/locks?term={term}&section_id={victim}", headers=admin2)


def test_delete_manual_section_and_lecture_cascade(client, admin):
    term, settings = "Fall 2026", {"target_term": "Fall 2026"}
    sched = lambda: client.post("/api/plan/schedule", json={"settings": settings}).json()
    body = {"term": term, "code": 3424, "section_no": 9, "modality": "In-Person", "sequence": "C", "cap": 30, "settings": settings}
    assert client.post("/api/plan/sections", json=body, headers=admin).status_code == 201
    sid = "ECON 3424-09"
    client.put("/api/plan/overrides", json={"term": term, "section_id": sid, "sequence": "D"}, headers=admin)
    r = client.delete(f"/api/plan/section?term={term}&section_id={sid}", headers=admin).json()
    assert r["kind"] == "manual" and r["after"] == {"section_id": sid, "override": None, "manual": None}
    assert r["before"]["manual"]["cap"] == 30 and r["before"]["override"]["sequence"] == "D"
    s = sched()
    assert sid not in {m["section_id"] for m in s["master"]} and s["manual_sections"] == [] and s["removed_sections"] == []
    # Undo re-creates it with the same ID and its drawer edit
    client.put("/api/plan/section-state", json={"term": term, "items": [{"state": r["before"], "expect": r["after"]}]}, headers=admin)
    row = next(m for m in sched()["master"] if m["section_id"] == sid)
    assert row["sequence"] == "D" and row["section_cap"] == 30 and row["match_basis"] == "Manual override"
    bad = {**r["before"], "section_id": "ECON 3424-55"}
    assert client.put("/api/plan/section-state", json={"term": term, "items": [{"state": bad}]}, headers=admin).status_code == 422
    client.delete(f"/api/plan/overrides?term={term}", headers=admin)
    # deleting a large lecture takes its linked recitations with it
    s = sched()
    rec = next((m for m in s["master"] if m["component"] == "Recitation" and m["linked_lecture"]), None)
    if rec:
        lec = rec["linked_lecture"]
        linked = {m["section_id"] for m in s["master"] if m["linked_lecture"] == lec}
        client.delete(f"/api/plan/section?term={term}&section_id={lec}", headers=admin)
        s2 = sched()
        assert not ({lec} | linked) & {m["section_id"] for m in s2["master"]}
        assert {x["section_id"] for x in s2["removed_sections"]} == {lec} | linked
        client.delete(f"/api/plan/overrides?term={term}&section_id={lec}", headers=admin)
        assert linked <= {m["section_id"] for m in sched()["master"]}
