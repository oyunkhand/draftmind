import pytest

from app.engine.draft import (DRAFT_ORDER, DraftError, DraftState, SeriesGame, assign_roles, fearless_locks,
                              fits_open_role)


def test_draft_order_is_pro_tournament_order():
    assert len(DRAFT_ORDER) == 20
    seq = [f"{s.side[0]}{s.type[0]}" for s in DRAFT_ORDER]
    assert seq == ["bb", "rb", "bb", "rb", "bb", "rb",          # ban phase 1
                   "bp", "rp", "rp", "bp", "bp", "rp",          # pick phase 1
                   "rb", "bb", "rb", "bb",                      # ban phase 2
                   "rp", "bp", "bp", "rp"]                      # pick phase 2
    assert [s.phase for s in DRAFT_ORDER].count("ban1") == 6
    assert [s.phase for s in DRAFT_ORDER].count("pick2") == 4
    assert DRAFT_ORDER[0].label == "B1 ban" and DRAFT_ORDER[19].label == "R5 pick"
    for side in ("blue", "red"):
        assert sum(1 for s in DRAFT_ORDER if s.side == side and s.type == "ban") == 5
        assert sum(1 for s in DRAFT_ORDER if s.side == side and s.type == "pick") == 5


def test_apply_undo_and_completion():
    st = DraftState("AAA", "BBB")
    assert st.current.label == "B1 ban"
    st.apply("Azir")
    assert st.current.label == "R1 ban"
    assert st.bans("blue") == ["Azir"]
    assert st.undo() == "Azir"
    assert st.index == 0
    champs = ["Azir", "Orianna", "Kaisa", "Varus", "Rell", "Rakan",
              "Vi", "Sejuani", "Gnar", "Ahri", "Ezreal", "Nautilus",
              "Yone", "Jax", "Sylas", "Corki",
              "Renekton", "Leona", "Jinx", "Viktor"]
    for c in champs:
        st.apply(c)
    assert st.complete and st.current is None
    assert st.picks("blue") == ["Vi", "Ahri", "Ezreal", "Leona", "Jinx"]
    assert st.picks("red") == ["Sejuani", "Gnar", "Nautilus", "Renekton", "Viktor"]
    with pytest.raises(DraftError):
        st.apply("Aatrox")


def test_cannot_take_champion_twice_or_unknown():
    st = DraftState("AAA", "BBB")
    st.apply("Azir")
    with pytest.raises(DraftError, match="already"):
        st.apply("Azir")
    with pytest.raises(DraftError, match="unknown"):
        st.apply("NotAChampion")


def test_serialization_roundtrip():
    st = DraftState("AAA", "BBB", ["Azir", "Vi"], "hard", {"blue": ["Jax"], "red": ["Jax"]})
    st2 = DraftState.from_dict(st.to_dict())
    assert st2.to_dict() == st.to_dict()
    assert st2.timeline()[2]["current"] is True


def test_role_assignment_handles_flex_picks():
    # Corki is mid/bot; with Azir (mid only) Corki must move to bot.
    a = assign_roles(["Corki", "Azir"])
    assert a["mid"] == "Azir" and a["bot"] == "Corki"
    assert fits_open_role(["Corki"], "Azir") == "mid"
    # Mid and bot both filled by mono-role champions -> Corki no longer fits.
    assert fits_open_role(["Azir", "Varus"], "Corki") is None
    assert fits_open_role(["Gnar", "Vi", "Azir", "Varus", "Rakan"], "Jax") is None


def test_open_roles():
    st = DraftState("AAA", "BBB", ["a"] * 0)
    for c in ["Teemo", "Shaco", "Singed", "Rammus", "Nunu", "Zilean", "Vi"]:
        st.apply(c)
    assert st.open_roles("blue") == ["top", "mid", "bot", "support"]


def test_fearless_hard_locks_both_teams():
    prev = [SeriesGame("AAA", "BBB", ["Azir", "Vi"], ["Orianna", "Kaisa"])]
    locks = fearless_locks(prev, "BBB", "AAA", "hard")
    assert locks["blue"] == locks["red"] == sorted(["Azir", "Vi", "Orianna", "Kaisa"])
    st = DraftState("BBB", "AAA", fearless_mode="hard", locked=locks)
    with pytest.raises(DraftError, match="both teams"):
        st.apply("Azir")  # banning a champion nobody can pick is pointless -> rejected
    st.apply("Jax")
    assert not st.is_available("Orianna", "blue", "pick")


def test_fearless_soft_only_locks_own_picks():
    prev = [SeriesGame("AAA", "BBB", ["Azir"], ["Orianna"]),
            SeriesGame("BBB", "AAA", ["Kaisa"], ["Vi"])]
    locks = fearless_locks(prev, "AAA", "BBB", "soft")
    assert locks["blue"] == ["Azir", "Vi"]          # AAA's own previous picks
    assert locks["red"] == ["Kaisa", "Orianna"]
    st = DraftState("AAA", "BBB", fearless_mode="soft", locked=locks)
    assert st.is_available("Azir", "red", "pick")    # BBB may still take AAA's champion
    assert not st.is_available("Azir", "blue", "pick")
    assert st.is_available("Azir", "blue", "ban")    # and AAA can ban it


def test_fearless_off_and_invalid_mode():
    prev = [SeriesGame("AAA", "BBB", ["Azir"], ["Orianna"])]
    assert fearless_locks(prev, "AAA", "BBB", "off") == {"blue": [], "red": []}
    with pytest.raises(DraftError):
        fearless_locks(prev, "AAA", "BBB", "extreme")


def test_next_step_for_side():
    st = DraftState("AAA", "BBB")
    assert st.next_step_for("red").label == "R1 ban"
    assert st.next_step_for("red", "pick").label == "R1 pick"
    assert st.side_of("BBB") == "red"
    with pytest.raises(DraftError):
        st.side_of("ZZZ")
