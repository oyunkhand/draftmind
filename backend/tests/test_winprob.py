from app.engine import winprob
from app.engine.draft import DraftState
from app.engine.stats import get_index


def test_probability_curve_and_what_if(client):
    idx = get_index()
    st = DraftState("NMB", "IWF")
    p0 = winprob.predict(idx, st, "blue")["p"]
    assert 0 < p0 < 1
    # symmetric: our chance on blue + their chance on red = 1
    assert abs(p0 + winprob.predict(idx, st, "red")["p"] - 1) < 1e-9
    for c in ["Aatrox", "Ahri", "Akali", "Alistar", "Amumu", "Anivia"]:
        st.apply(c)
    assert len(winprob.curve(idx, st, "blue")) == 7
    assert st.current.type == "pick"
    deltas = winprob.what_if(idx, st, "blue", ["Ezreal", "Leona"])
    assert set(deltas) == {"Ezreal", "Leona"}


def test_analysis_includes_win_probability(client):
    g = client.post("/api/drafts", json={"our_team": "NMB", "opponent": "IWF"}).json()
    a = client.get(f"/api/drafts/{g['id']}").json()
    wp = a["win_probability"]
    assert 0 < wp["p"] < 1 and wp["curve"][0]["label"] == "start"
