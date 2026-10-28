import html, json, os, re, sys, time
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TOOL_ID = os.getenv("CROUS_TOOL_ID", "47")
# "house_sharing" = colocation ; mets OCCUPATION="" pour tous les types
OCCUPATION = os.getenv("OCCUPATION", "house_sharing")
RUN_SECONDS = int(os.getenv("RUN_SECONDS", "0"))  # 0 = tourne sans fin
INTERVAL = int(os.getenv("INTERVAL", "60"))
STATE = "state.json"

BASE = "https://trouverunlogement.lescrous.fr"
SEARCH_URL = f"{BASE}/tools/{TOOL_ID}/search"
# ZONE="france" = tous les Crous (pour tester) ; sinon Marseille
FRANCE = os.getenv("ZONE", "marseille").lower() == "france"
LIEU = "France" if FRANCE else "Marseille"
PARAMS = {}
if not FRANCE:
    PARAMS = {
        "bounds": "5.2286902_43.3910329_5.5324758_43.1696205",
        "locationName": "Marseille (13000)",
    }
if OCCUPATION:
    PARAMS["occupationModes"] = OCCUPATION


def fetch():
    r = requests.get(
        SEARCH_URL, params=PARAMS, headers={"User-Agent": "Mozilla/5.0"}, timeout=20
    )
    r.raise_for_status()
    page = r.text
    if not FRANCE and re.search(r"logements? trouvés? en France", page):
        raise RuntimeError("Filtre Marseille non appliqué par le site (résultats pour toute la France)")
    items = {}
    for m in re.finditer(r'href="[^"]*?/accommodations/(\d+)"[^>]*>([^<]*)<', page):
        name = html.unescape(m.group(2)).strip()
        if m.group(1) not in items or (name and not items[m.group(1)]):
            items[m.group(1)] = name
    return items


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
    print(f"{len(items)} logement(s) trouvé(s) : {sorted(items)}", flush=True)
    new = [i for i in items if i not in seen]
    for i in new[:10]:
        name = items[i] or "Logement"
        notify(f"🏠 Logement CROUS disponible ({LIEU})\n{name}\n{BASE}/tools/{TOOL_ID}/accommodations/{i}")
    # on ne garde que les logements actuellement affichés : s'il disparaît puis revient, on re-alerte
    seen.clear()
    seen.update(items)
    save(seen)
    return len(items)


def main():
    seen = load()
    start = time.time()
    first = True
    while True:
        try:
            n = check(seen)
            if first and os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
                notify(f"✅ Bot démarré : {n} logement(s) trouvé(s) pour l'instant ({LIEU}).")
        except Exception as e:
            print("Erreur :", e, file=sys.stderr, flush=True)
            if first and os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
                notify(f"⚠️ Bot démarré mais erreur de recherche : {e}")
        first = False
        if RUN_SECONDS and time.time() - start + INTERVAL > RUN_SECONDS:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
