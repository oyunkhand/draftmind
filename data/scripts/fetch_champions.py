"""Snapshot champion metadata from Riot Data Dragon (public CDN) into data/champions.json.

Riot's data does not include pro-play positions, so we merge a hand-curated role map.
Run:  python3 data/scripts/fetch_champions.py
"""
import json
import os
import urllib.request

DD = "https://ddragon.leagueoflegends.com"
OUT = os.path.join(os.path.dirname(__file__), "..", "champions.json")

# Curated pro-play positions (first entry = primary role).
ROLE_MAP = {
    # --- top ---
    "Aatrox": ["top"], "Ambessa": ["top", "mid"], "Gnar": ["top"], "Jax": ["top", "jungle"],
    "KSante": ["top"], "Renekton": ["top", "mid"], "Rumble": ["top", "jungle", "mid"], "Ornn": ["top"],
    "Camille": ["top", "support"], "Gwen": ["top", "jungle"], "Jayce": ["top", "mid"], "Sion": ["top"],
    "Aurora": ["mid", "top"], "Gragas": ["top", "jungle", "support"], "Kennen": ["top"],
    "Gangplank": ["top"], "Fiora": ["top"], "Yone": ["mid", "top"], "Poppy": ["jungle", "support", "top"],
    "Kled": ["top"], "Sett": ["top", "support"], "Darius": ["top"], "Mordekaiser": ["top"],
    "Riven": ["top"], "Malphite": ["top", "support"], "Urgot": ["top"], "Vladimir": ["mid", "top"],
    "Zac": ["jungle", "top"], "Skarner": ["jungle", "top"], "Yorick": ["top"], "DrMundo": ["top"],
    "Irelia": ["top", "mid"], "TahmKench": ["top", "support"], "Chogath": ["top"], "Shen": ["top", "support"],
    "Garen": ["top"], "Olaf": ["top", "jungle"], "Zaahen": ["top"],
    # --- jungle ---
    "Vi": ["jungle"], "XinZhao": ["jungle"], "Sejuani": ["jungle"], "Maokai": ["jungle", "support"],
    "LeeSin": ["jungle"], "MonkeyKing": ["jungle", "top"], "Viego": ["jungle"], "Nidalee": ["jungle"],
    "JarvanIV": ["jungle"], "Pantheon": ["jungle", "support", "top"], "Nocturne": ["jungle"],
    "RekSai": ["jungle"], "Kindred": ["jungle"], "Graves": ["jungle"], "Lillia": ["jungle"],
    "Ivern": ["jungle"], "Elise": ["jungle"], "Taliyah": ["jungle", "mid"], "Brand": ["jungle", "support"],
    "Diana": ["jungle", "mid"], "Zyra": ["support", "jungle"], "Trundle": ["jungle", "top"],
    "Volibear": ["jungle", "top"], "Belveth": ["jungle"], "Briar": ["jungle"],
    "Kayn": ["jungle"], "Hecarim": ["jungle"], "Udyr": ["jungle", "top"], "Nunu": ["jungle"],
    "Ekko": ["jungle", "mid"], "Karthus": ["jungle"], "Amumu": ["jungle", "support"],
    # --- mid ---
    "Azir": ["mid"], "Orianna": ["mid"], "Ahri": ["mid"], "Sylas": ["mid", "jungle"],
    "Corki": ["mid", "bot"], "Akali": ["mid", "top"], "Leblanc": ["mid"], "Syndra": ["mid"],
    "Viktor": ["mid"], "Tristana": ["mid", "bot"], "Galio": ["mid", "support"], "Hwei": ["mid", "support"],
    "Ryze": ["mid", "top"], "Annie": ["mid"], "Cassiopeia": ["mid"], "AurelionSol": ["mid"],
    "Zoe": ["mid"], "Smolder": ["bot", "mid"], "Ziggs": ["bot", "mid"], "Vex": ["mid"],
    "Yasuo": ["mid", "bot", "top"], "TwistedFate": ["mid"], "Mel": ["mid", "support"],
    "Lissandra": ["mid"], "Swain": ["support", "mid", "bot"], "Naafiri": ["mid"], "Zed": ["mid"],
    "Qiyana": ["mid"], "Anivia": ["mid"], "Xerath": ["mid", "support"],
    "Velkoz": ["mid", "support"], "Malzahar": ["mid"], "Katarina": ["mid"], "Kassadin": ["mid"],
    # --- bot ---
    "Kaisa": ["bot"], "Varus": ["bot"], "Ezreal": ["bot"], "Xayah": ["bot"], "Zeri": ["bot"],
    "Jinx": ["bot"], "Aphelios": ["bot"], "Kalista": ["bot"], "Ashe": ["bot", "support"],
    "Jhin": ["bot"], "Caitlyn": ["bot"], "Lucian": ["bot"], "Sivir": ["bot"], "Draven": ["bot"],
    "MissFortune": ["bot"], "KogMaw": ["bot"], "Yunara": ["bot"], "Nilah": ["bot"], "Samira": ["bot"],
    "Twitch": ["bot"], "Vayne": ["bot"], "Senna": ["support", "bot"],
    # --- support ---
    "Rakan": ["support"], "Nautilus": ["support"], "Leona": ["support"], "Alistar": ["support"],
    "Rell": ["support"], "Braum": ["support"], "Renata": ["support"], "Lulu": ["support"],
    "Thresh": ["support"], "Bard": ["support"], "Karma": ["support", "mid"], "Milio": ["support"],
    "Neeko": ["support", "mid"], "Pyke": ["support"], "Blitzcrank": ["support"],
    "Seraphine": ["support", "bot"], "Nami": ["support"], "Janna": ["support"], "Yuumi": ["support"],
    "Soraka": ["support"], "Taric": ["support"], "Lux": ["support", "mid"], "Morgana": ["support"],
    "Sona": ["support"], "Zilean": ["support"],
}

TAG_TO_ROLE = {"Marksman": "bot", "Support": "support", "Mage": "mid", "Assassin": "mid",
               "Fighter": "top", "Tank": "top"}


def main():
    versions = json.load(urllib.request.urlopen(DD + "/api/versions.json"))
    ver = versions[0]
    data = json.load(urllib.request.urlopen(f"{DD}/cdn/{ver}/data/en_US/champion.json"))["data"]
    out = []
    for cid, c in sorted(data.items()):
        roles = ROLE_MAP.get(cid) or [TAG_TO_ROLE.get(c["tags"][0], "mid")]
        out.append({
            "id": cid, "key": int(c["key"]), "name": c["name"], "title": c["title"],
            "tags": c["tags"], "roles": roles, "curated": cid in ROLE_MAP,
        })
    with open(OUT, "w") as f:
        json.dump({"version": ver, "champions": out}, f, indent=1)
    print(f"wrote {len(out)} champions (Data Dragon {ver}) -> {os.path.abspath(OUT)}")


if __name__ == "__main__":
    main()
