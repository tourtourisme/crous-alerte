import html, json, os, re, sys, time
from urllib.parse import urlparse, parse_qs
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
RUN_SECONDS = int(os.getenv("RUN_SECONDS", "0"))  # 0 = tourne sans fin
INTERVAL = int(os.getenv("INTERVAL", "60"))
STATE = "state.json"

BASE = "https://trouverunlogement.lescrous.fr"
# Lien surveillé tant que tu n'en as pas envoyé un autre au bot
DEFAULT_URL = os.getenv(
    "DEFAULT_URL",
    BASE + "/tools/47/search?bounds=5.2286902_43.3910329_5.5324758_43.1696205"
    "&locationName=Marseille+%2813000%29",
)
HEADERS = {"User-Agent": "Mozilla/5.0"}


def tg(method, **data):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data, timeout=30)
        return r.json()
    except Exception as e:
        print("Erreur Telegram :", e, file=sys.stderr, flush=True)
        return {}


def notify(text):
    tg("sendMessage", chat_id=CHAT_ID, text=text)


def load():
    try:
        d = json.load(open(STATE))
    except Exception:
        d = {}
    if isinstance(d, list):  # ancien format
        d = {"seen": d}
    d.setdefault("url", DEFAULT_URL)
    d.setdefault("seen", [])
    d.setdefault("offset", 0)
    return d


def save(st):
    json.dump(st, open(STATE, "w"))


def parse_url(url):
    u = urlparse(url)
    m = re.fullmatch(r"/tools/(\d+)/search", u.path)
    if u.scheme != "https" or u.netloc != "trouverunlogement.lescrous.fr" or not m:
        return None
    return m.group(1), parse_qs(u.query)


def place_name(url):
    return parse_qs(urlparse(url).query).get("locationName", ["toute la France"])[0]


def fetch(url):
    tool, params = parse_url(url)
    r = requests.get(f"{BASE}/tools/{tool}/search", params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    page = r.text
    if "bounds" in params and re.search(r"logements? trouvés? en France", page):
        raise RuntimeError("le site n'a pas appliqué la zone du lien (résultats pour toute la France)")
    items = {}
    for m in re.finditer(r'href="[^"]*?/accommodations/(\d+)"[^>]*>([^<]*)<', page):
        name = html.unescape(m.group(2)).strip()
        if m.group(1) not in items or (name and not items[m.group(1)]):
            items[m.group(1)] = name
    return tool, items


def handle_updates(st):
    """Lit les messages Telegram : '/start <lien>' ou un lien seul change la zone surveillée."""
    res = tg("getUpdates", offset=st["offset"], timeout=0).get("result", [])
    for u in res:
        st["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != CHAT_ID:
            continue  # ignore tout sauf ton chat
        text = (msg.get("text") or "").strip()
        m = re.search(r"https://\S+", text)
        if m:
            url = m.group(0)
            if parse_url(url):
                st["url"], st["seen"] = url, []
                notify(f"✅ Surveillance activée : {place_name(url)}\nVérification chaque minute.")
            else:
                notify("❌ Lien non reconnu. Envoie un lien de recherche du type "
                       "trouverunlogement.lescrous.fr/tools/…/search?…")
        elif text.startswith(("/start", "/status")):
            notify(f"Surveillance actuelle : {place_name(st['url'])}\n"
                   "Pour changer de zone : /start suivi du lien de recherche.")
    save(st)


def check(st):
    tool, items = fetch(st["url"])
    print(f"{len(items)} logement(s) trouvé(s) ({place_name(st['url'])}) : {sorted(items)}", flush=True)
    seen = set(st["seen"])
    for i in [i for i in items if i not in seen][:10]:
        notify(f"🏠 Logement CROUS disponible ({place_name(st['url'])})\n"
               f"{items[i] or 'Logement'}\n{BASE}/tools/{tool}/accommodations/{i}")
    st["seen"] = sorted(items)  # oublie ceux qui disparaissent : ils re-alertent s'ils reviennent
    save(st)
    return len(items)


def main():
    st = load()
    start = time.time()
    first = True
    manual = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
    while True:
        try:
            handle_updates(st)
            n = check(st)
            if first and manual:
                notify(f"✅ Bot démarré : {n} logement(s) trouvé(s) pour l'instant ({place_name(st['url'])}).")
        except Exception as e:
            print("Erreur :", e, file=sys.stderr, flush=True)
            if first and manual:
                notify(f"⚠️ Bot démarré mais erreur de recherche : {e}")
        first = False
        if RUN_SECONDS and time.time() - start + INTERVAL > RUN_SECONDS:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
