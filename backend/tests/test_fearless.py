from app.engine.fearless import ban_impact, fearless_profile


def _m(i, game_number, winner, a_pick, banned):
    """Team A (blue) vs B (red); A picks a_pick; `banned` is banned by B."""
    draft = [{"seq": 0, "side": "red", "type": "ban", "team": "B", "champion": banned},
             {"seq": 1, "side": "blue", "type": "pick", "team": "A", "champion": a_pick}]
    return {"id": f"g{i}", "series_id": f"s{i // 3}", "game_number": game_number, "blue_team": "A", "red_team": "B",
            "winner": winner, "draft": draft,
            "participants": [{"team": "A", "side": "blue", "player": "p1", "role": "mid", "champion": a_pick}]}


def test_ban_impact_finds_the_ban_that_hurts():
    ms = []
    for i in range(30):  # A wins with Ahri; when B bans Ahri (every 3rd game) A loses
        banned = i % 3 == 0
        ms.append(_m(i, i % 3 + 1, "B" if banned else "A", "Zed" if banned else "Ahri", "Ahri" if banned else "Teemo"))
    r = ban_impact(ms, "A", min_banned=4)
    assert r["items"] and r["items"][0]["champion"] == "Ahri"
    assert r["items"][0]["wr_when_banned"] == 0.0 and r["items"][0]["delta"] < -0.5


def test_fearless_profile_buckets_and_shifts():
    ms = [_m(i, i % 3 + 1, "A" if i % 3 == 0 else "B", "Ahri", "Teemo") for i in range(30)]
    f = fearless_profile(ms, "A")
    assert [b["game"] for b in f["buckets"]] == ["G1", "G2", "G3+"]
    assert f["buckets"][0]["wr"] == 1.0 and f["buckets"][2]["wr"] == 0.0
    assert f["shifts"] and "Game 1" in f["shifts"][0]


def test_scouting_report_includes_fearless_sections(client):
    r = client.get("/api/teams/IWF/scouting?vs=NMB").json()
    assert "fearless" in r and "ban_impact" in r
    md = client.get("/api/teams/IWF/scouting.md").text
    assert "Scouting Report" in md
