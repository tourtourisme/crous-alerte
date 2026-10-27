import json, os, sys, time
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TOOL_ID = os.getenv("CROUS_TOOL_ID", "47")
RUN_SECONDS = int(os.getenv("RUN_SECONDS", "0"))  # 0 = tourne sans fin
INTERVAL = int(os.getenv("INTERVAL", "60"))
STATE = "state.json"

URL = f"https://trouverunlogement.lescrous.fr/api/fr/search/{TOOL_ID}"
BODY = {
    "idTool": int(TOOL_ID),
    "need_aggregation": True,
    "page": 1,
    "pageSize": 24,
    "sector": None,
    "occupationModes": [],  # [] = tous les types de logement
    # rectangle autour de Marseille (haut-gauche, bas-droite)
    "location": [{"lon": 5.2286902, "lat": 43.3910329}, {"lon": 5.5324758, "lat": 43.1696205}],
    "residence": None,
    "precision": 5,
    "equipment": [],
    "price": {"max": 10000},
    "area": {"min": 0},
    "toolMechanism": "flow",
}


def fetch():
    r = requests.post(URL, json=BODY, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    return r.json()["results"]["items"]


def notify(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text},
        timeout=20,
    )


def load():
    try:
        return set(json.load(open(STATE)))
    except Exception:
        return set()


def save(seen):
    json.dump(sorted(seen), open(STATE, "w"))


def check(seen):
    items = fetch()
    new = [i for i in items if str(i["id"]) not in seen]
    for i in new[:10]:
        name = i.get("label") or i.get("residence", {}).get("label", "Logement")
        link = f"https://trouverunlogement.lescrous.fr/tools/{TOOL_ID}/accommodations/{i['id']}"
        notify(f"🏠 Logement CROUS disponible à Marseille\n{name}\n{link}")
    seen.update(str(i["id"]) for i in items)
    save(seen)


def main():
    seen = load()
    start = time.time()
    while True:
        try:
            check(seen)
        except Exception as e:
            print("Erreur :", e, file=sys.stderr)
        if RUN_SECONDS and time.time() - start + INTERVAL > RUN_SECONDS:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
