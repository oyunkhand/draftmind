def _play_to_end(client, gid, a):
    while not a["state"]["complete"]:
        if a["state"]["current"]["ours"]:
            top = a["recommendations"]["recommendations"][0]["champion"]
            a = client.post(f"/api/drafts/{gid}/decisions", json={"champion": top, "decision": "accept"}).json()
        else:
            top = a["prediction"]["predictions"][0]["champion"]
            a = client.post(f"/api/drafts/{gid}/actions", json={"champion": top}).json()
    return a


def test_health_and_reference_data(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["data_source"] == "sample" and h["llm_provider"] == "none"
    assert len(client.get("/api/teams").json()) >= 6
    assert len(client.get("/api/draft-order").json()) == 20
    assert len(client.get("/api/champions").json()["champions"]) > 150


def test_scouting_report_and_markdown(client):
    r = client.get("/api/teams/IWF/scouting?vs=NMB").json()
    assert len(r["players"]) == 5 and r["insights"] and r["ban_plan"]
    assert r["summary"]["objectives"]["first_dragon"]["rate"] is not None
    md = client.get("/api/teams/IWF/scouting.md")
    assert md.status_code == 200 and md.text.startswith("# Scouting Report — Iron Wolves")
    assert client.get("/api/teams/NOPE/scouting").status_code == 404


def test_dashboard_ban_plan(client):
    dashboard = client.get("/api/dashboard?our=NMB&opp=IWF").json()
    assert len(dashboard["ban_plan"]) <= 5
    assert all(entry["champion"] for entry in dashboard["ban_plan"])


def test_full_series_with_decisions_and_fearless(client):
    s = client.post("/api/series", json={"our_team": "NMB", "opponent": "IWF", "best_of": 3, "fearless_mode": "hard"}).json()
    g = client.post(f"/api/series/{s['id']}/games", json={"our_side": "blue"}).json()
    gid = g["id"]
    a = client.get(f"/api/drafts/{gid}").json()
    assert a["state"]["current"]["label"] == "B1 ban" and a["state"]["current"]["ours"]
    recs = a["recommendations"]["recommendations"]

    # Reject: logged, champion disappears from this step's suggestions, draft does not advance.
    a = client.post(f"/api/drafts/{gid}/decisions", json={"champion": recs[0]["champion"], "decision": "reject"}).json()
    assert a["state"]["index"] == 0 and recs[0]["champion"] in a["rejected_this_step"]
    assert recs[0]["champion"] not in [r["champion"] for r in a["recommendations"]["recommendations"]]

    # Modify: coach overrides with their own champion.
    a = client.post(f"/api/drafts/{gid}/decisions",
                    json={"champion": recs[1]["champion"], "decision": "modify", "final_champion": "Kalista"}).json()
    assert a["state"]["timeline"][0]["champion"] == "Kalista"

    # Not our turn -> 400
    r = client.post(f"/api/drafts/{gid}/decisions", json={"champion": "Azir", "decision": "accept"})
    assert r.status_code == 400

    # Undo / redo via actions
    client.post(f"/api/drafts/{gid}/actions", json={"champion": "Azir"})
    a = client.post(f"/api/drafts/{gid}/undo").json()
    assert a["state"]["index"] == 1

    a = _play_to_end(client, gid, a)
    blue_picks = [t["champion"] for t in a["state"]["timeline"] if t["type"] == "pick"]
    assert len(blue_picks) == 10
    client.post(f"/api/drafts/{gid}/result", json={"result": "win"})

    # Game 2: every champion picked in game 1 is locked for both teams.
    g2 = client.post(f"/api/series/{s['id']}/games", json={"our_side": "red"}).json()
    a2 = client.get(f"/api/drafts/{g2['id']}").json()
    assert sorted(a2["locked"]["blue"]) == sorted(blue_picks) == sorted(a2["locked"]["red"])
    pred = [p["champion"] for p in a2["prediction"]["predictions"]]
    assert not set(pred) & set(blue_picks) or a2["prediction"]["step"]["type"] == "ban"
    r = client.post(f"/api/drafts/{g2['id']}/actions", json={"champion": blue_picks[0]})
    assert r.status_code == 400

    series = client.get(f"/api/series/{s['id']}").json()
    assert series["score"] == [1, 0] and len(series["games"]) == 2
    kinds = {d["decision"] for d in series["games"][0]["decisions"]}
    assert {"reject", "modify", "accept"} <= kinds

    # Explain works without any API key (templated).
    first = a2["prediction"]["predictions"][0]["champion"]
    e = client.post(f"/api/drafts/{g2['id']}/explain", json={"champion": first, "kind": "prediction"}).json()
    assert e["source"] == "template" and e["text"]


def test_weights_roundtrip(client):
    w = client.put("/api/settings/weights", json={"pick": {"comfort": 2.5}}).json()["weights"]
    assert w["pick"]["comfort"] == 2.5
    w = client.post("/api/settings/weights/reset").json()["weights"]
    assert w["pick"]["comfort"] == 1.3


def test_backtest_beats_baseline(client):
    bt = client.get("/api/model/backtest").json()
    assert bt["pick"]["top5"] > bt["pick"]["baseline_top5"]
    assert bt["ban"]["top5"] > bt["ban"]["baseline_top5"]


def test_validation_errors(client):
    assert client.post("/api/series", json={"our_team": "NMB", "opponent": "NMB"}).status_code == 400
    assert client.post("/api/series", json={"our_team": "NMB", "opponent": "IWF", "fearless_mode": "x"}).status_code == 400
    assert client.get("/api/drafts/nope").status_code == 404
