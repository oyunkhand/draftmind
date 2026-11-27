from app.engine.draft import DraftState, draft_order
from app.engine.selection import first_selection_advice


def test_red_first_order_mirrors_blue_first():
    blue, red = draft_order("blue"), draft_order("red")
    assert [s.side for s in red] == ["red" if s.side == "blue" else "blue" for s in blue]
    assert red[0].label == "R1 ban" and red[6].label == "R1 pick"


def test_state_with_red_first_attributes_actions_to_red():
    st = DraftState("AAA", "BBB", first_side="red")
    st.apply("Aatrox")
    assert st.bans("red") == ["Aatrox"] and st.bans("blue") == []
    assert DraftState.from_dict(st.to_dict()).first_side == "red"


def _m(i, blue, red, winner, first):
    other = "red" if first == "blue" else "blue"
    return {"id": f"g{i}", "tournament": "Test League 2026 — Split", "blue_team": blue, "red_team": red,
            "winner": winner, "draft": [{"seq": 0, "side": first}, {"seq": 1, "side": other}]}


def test_first_selection_prefers_the_side_that_wins():
    ms = []
    for i in range(40):  # blue side wins 3 of 4 games whoever drafts first
        first = "red" if i % 2 else "blue"
        blue, red = ("A", "B") if i % 2 else ("B", "A")
        ms.append(_m(i, blue, red, blue if i % 4 else red, first))
    r = first_selection_advice(ms, "A", "B")
    assert r["available"] and r["recommendation"] == "blue side"
    assert r["choices"][0]["wr"] > 0.6 and len(r["choices"]) == 4


def test_no_first_selection_era():
    ms = [_m(i, "A", "B", "A", "blue") for i in range(5)]
    assert first_selection_advice(ms, "A", "B")["available"] is False


def test_api_game_with_red_first(client):
    s = client.post("/api/series", json={"our_team": "NMB", "opponent": "IWF", "best_of": 3}).json()
    g = client.post(f"/api/series/{s['id']}/games", json={"our_side": "blue", "first_side": "red"}).json()
    a = client.get(f"/api/drafts/{g['id']}").json()
    assert a["state"]["timeline"][0]["side"] == "red"
    assert client.get("/api/draft-order?first_side=red").json()[0]["side"] == "red"
    assert client.get("/api/first-selection?our=NMB&opp=IWF").status_code == 200
