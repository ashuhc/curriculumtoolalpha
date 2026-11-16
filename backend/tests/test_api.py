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
    # Spring 2027 ECON 1116 mixes 200- and 45-seat sections: the 45s add no recitations
    row = next(r for r in d["demand"] if r["code"] == 1116 and not r["virtual"])
    assert "45" in row["section_caps"] and rec[1126]["planned_sections"] < -(-row["projected_enrollment"] // 30)
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
