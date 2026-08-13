"""
Morning Intelligence Report Generator (v2)
-------------------------------------------
Liest RSS-Feeds aus mehreren Kategorien, laesst Gemini einen kompakten,
kategorisierten Bericht schreiben, holt zusaetzlich Kursdaten, einen
Wissens-Fakt des Tages und historische Ereignisse - und schreibt alles
als index.html plus ein Kalender-Archiv unter reports/.
"""

import os
import re
import json
import html
import calendar
import datetime
import feedparser
import requests
from google import genai

# ---------------------------------------------------------
# 1. QUELLEN PRO KATEGORIE
#    Reihenfolge hier = Reihenfolge im Report.
# ---------------------------------------------------------
CATEGORY_FEEDS = {
    "Kuenstliche Intelligenz": {
        "arXiv - KI Papers": "http://export.arxiv.org/rss/cs.AI",
        "Heise Online": "https://www.heise.de/newsticker/heise.rdf",
    },
    "Wirtschaft": {
        "Tagesschau - Wirtschaft": "https://www.tagesschau.de/wirtschaft/index~rss2.xml",
        "Handelsblatt": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen",
    },
    "Politik Deutschland": {
        "Tagesschau - Innenpolitik": "https://www.tagesschau.de/inland/innenpolitik/index~rss2.xml",
    },
    "Ausbildung & IT-Arbeitsmarkt": {
        "Golem.de": "https://rss.golem.de/rss.php?feed=RSS2.0",
    },
}

# Kategorien, zu denen die KI ausfuehrlicher schreiben soll (mehr Stichpunkte)
CATEGORIES_AUSFUEHRLICH = {"Kuenstliche Intelligenz", "Politik Deutschland"}

# Icon + Farbe pro Kategorie, fuer die Kartenoptik
CATEGORY_META = {
    "Kuenstliche Intelligenz": {"icon": "\U0001F916", "color": "#7c3aed"},
    "Wirtschaft": {"icon": "\U0001F4B9", "color": "#1e40af"},
    "Politik Deutschland": {"icon": "\U0001F3DB\uFE0F", "color": "#b91c1c"},
    "Ausbildung & IT-Arbeitsmarkt": {"icon": "\U0001F393", "color": "#0891b2"},
}

MAX_ITEMS_PER_FEED = 8

# ---------------------------------------------------------
# 2. WATCHLIST FUER KURSDATEN (yfinance-Ticker)
#    Einfach anpassen/ergaenzen.
# ---------------------------------------------------------
STOCK_TICKERS = {
    "DAX": "^GDAXI",
    "MSCI World (URTH)": "URTH",
    "MSCI EM IMI (EIMI.L)": "EIMI.L",
    "Bitcoin": "BTC-USD",
    "Apple": "AAPL",
    "Microsoft": "MSFT",
    "Nvidia": "NVDA",
    "Alphabet (Google)": "GOOGL",
    "Amazon": "AMZN",
    "Tesla": "TSLA",
    "SAP": "SAP.DE",
}

# Rotation fuer "Wissen des Tages": (Label, Icon, Kurzbeschreibung fuer den Prompt)
WISSEN_THEMEN = [
    ("Psychologie", "\U0001F9E0", "Denken, Verhalten, Gewohnheiten, Wahrnehmung"),
    ("Kommunikation & Menschen", "\U0001F5E3\uFE0F", "Koerpersprache, Gespraechsfuehrung, nonverbale Kommunikation, Konflikte, soziale Dynamiken"),
    ("Geografie & Kulturen", "\U0001F30D", "Laender, Kulturen, Braeuche, besondere Orte"),
    ("Geschichte", "\U0001F3DB\uFE0F", "interessante Ereignisse, Personen und historische Zusammenhaenge"),
    ("Wissenschaft", "\U0001F52C", "Physik, Chemie, Biologie, Astronomie usw."),
    ("Mensch & Koerper", "\U0001F9EC", "wie unser Koerper funktioniert, Sinne, Gehirn, Schlaf, Ernaehrung etc."),
    ("Alltagswissen", "\U0001F9E9", "Dinge, die man im Alltag staendig sieht oder benutzt, aber selten hinterfragt"),
]


# ---------------------------------------------------------
# FEEDS EINSAMMELN
# ---------------------------------------------------------
def collect_by_category():
    """Holt Feed-Eintraege, gruppiert nach Kategorie."""
    result = {}
    for category, feeds in CATEGORY_FEEDS.items():
        items = []
        for source_name, url in feeds.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                    items.append({
                        "source": source_name,
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", ""),
                        "link": entry.get("link", ""),
                    })
            except Exception as e:
                print(f"Warnung: Feed '{source_name}' ({category}) fehlgeschlagen: {e}")
        result[category] = items
    return result


# ---------------------------------------------------------
# PROMPT BAUEN UND GEMINI AUFRUFEN
# ---------------------------------------------------------
def build_prompt(items_by_category, wissen_thema, on_this_day_events, holiday_name, today_display):
    block = ""
    for category, items in items_by_category.items():
        block += f"\n=== {category} ===\n"
        if not items:
            block += "(keine aktuellen Meldungen gefunden)\n"
            continue
        for item in items:
            clean_summary = item["summary"].replace("\n", " ")[:200]
            block += f"- Titel: {item['title']}\n  Link: {item['link']}\n  Info: {clean_summary}\n"

    category_names = "\n".join(f"### {c}" for c in CATEGORY_FEEDS.keys())

    wissen_label, wissen_icon, wissen_desc = wissen_thema

    events_block = ""
    if on_this_day_events:
        events_block = "Historische Ereignisse zu diesem Datum (aus Wikipedia, als Grundlage nutzen):\n"
        for e in on_this_day_events:
            events_block += f"- {e.get('year')}: {e.get('text')}\n"
    holiday_block = f"Heutiger gesetzlicher Feiertag: {holiday_name}\n" if holiday_name else ""

    prompt = f"""Du bist ein persoenlicher Nachrichtenassistent fuer einen Informatik-Azubi,
der sich fuer KI interessiert, in Aktien/ETFs investiert und deutsche Politik verfolgt.
Heutiges Datum: {today_display}

Hier sind Rohdaten aus mehreren Kategorien:
{block}

AUFGABE:
Schreibe fuer JEDE der folgenden Kategorien einen eigenen Abschnitt, mit EXAKT diesen
Ueberschriften (### gefolgt vom Kategorienamen, keine Abweichung):

{category_names}
### Wissen des Tages
### Besonderer Tag heute

REGELN:
- WICHTIGSTE REGEL: Waehle bewusst nur die WIRKLICH relevanten/wichtigen Meldungen aus den
  Rohdaten aus - liste NICHT einfach alles auf, was in den Feeds steht. Lieber 2 wirklich
  informative Punkte als 5 belanglose. Lass Nebensaechliches, Boulevard-Themen oder
  Meldungen ohne echten Neuigkeitswert komplett weg.
- Nur STICHPUNKTE, keine langen Saetze (max. ca. 15 Woerter pro Stichpunkt)
- Jeder Stichpunkt mit Quellenlink im Markdown-Format: - [Kurztitel](URL): Kernaussage
- Standardmaessig 2-4 Stichpunkte pro Kategorie (nur so viele, wie wirklich relevant sind)
- Bei "Kuenstliche Intelligenz" und "Politik Deutschland": AUSFUEHRLICHER schreiben,
  bis zu 5-8 Stichpunkte, aber NUR falls tatsaechlich so viele relevante Meldungen da sind
- Bei "Kuenstliche Intelligenz": explizit erwaehnen, was neue Modelle/Tools koennen UND
  moegliche Risiken/Gefahren, wenn relevant
- Wenn eine Kategorie keine Meldungen hat, schreibe einen einzelnen Punkt "- Heute keine relevanten Meldungen"
- Bei "Wirtschaft": NUR Wirtschaftspolitik, Unternehmensnachrichten, Konjunktur, Zinsen/EZB
  behandeln - KEINE Kurse/Marktbewegungen nennen (die stehen schon in einer separaten
  Marktdaten-Tabelle, nicht doppeln). Keine Kauf-/Verkaufsempfehlungen aussprechen.
- "Wissen des Tages": schreibe 2-3 kompakte Stichpunkte mit einem interessanten Fakt
  zum Thema "{wissen_label}" ({wissen_desc}) - aus eigenem Wissen, unabhaengig von den Feeds
- "Besonderer Tag heute": {events_block}{holiday_block}
  Schreibe 2-4 kompakte Stichpunkte zu Feiertagen, Gedenktagen, Welttagen ("Weltkindertag" etc.)
  oder aussergewoehnlichen Ereignissen (z.B. Sonnenfinsternis) fuer dieses Datum. Nutze die
  historischen Ereignisse oben als Grundlage, ergaenze bekannte wiederkehrende Gedenk-/Welttage
  aus eigenem Wissen. Astronomische Ereignisse NUR erwaehnen, wenn du dir wirklich sicher bist,
  sonst weglassen. Falls nichts Besonderes bekannt ist, schreibe "- Kein besonderer Anlass bekannt"
- Keine Einleitung, keine Zusammenfassung am Ende - nur die Abschnitte selbst
"""
    return prompt


def get_summary(prompt):
    """Schickt den Prompt an die Gemini API und gibt den Antworttext zurueck."""
    api_key = os.environ["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
    )
    return response.text


def parse_categorized_response(text):
    """Teilt die Gemini-Antwort anhand der '### Kategorie'-Marker auf."""
    sections = {}
    current = None
    buffer = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("### "):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = stripped[4:].strip()
            buffer = []
        else:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()
    return sections


# ---------------------------------------------------------
# MARKDOWN (STICHPUNKTE + LINKS) -> HTML
# ---------------------------------------------------------
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def render_bullets(markdown_text):
    """Wandelt einfache Stichpunkt-Listen mit [Text](URL)-Links in HTML um."""
    lines = [l.strip() for l in markdown_text.split("\n") if l.strip()]
    html_out = "<ul>"
    for line in lines:
        content = line[2:] if line.startswith(("- ", "* ")) else line

        def replace_link(m):
            safe_text = html.escape(m.group(1))
            safe_url = html.escape(m.group(2), quote=True)
            return f'<a href="{safe_url}" target="_blank" rel="noopener">{safe_text}</a>'

        escaped = html.escape(content)
        # escape() hat die Klammern/Slashes im Link kaputt escaped - Links deshalb
        # vor dem escapen extrahieren und danach wieder einsetzen:
        placeholders = {}
        def stash_link(m):
            key = f"@@LINK{len(placeholders)}@@"
            placeholders[key] = replace_link(m)
            return key
        content_stashed = LINK_PATTERN.sub(stash_link, content)
        escaped = html.escape(content_stashed)
        for key, val in placeholders.items():
            escaped = escaped.replace(html.escape(key), val)
        html_out += f"<li>{escaped}</li>"
    html_out += "</ul>"
    return html_out


# ---------------------------------------------------------
# KURSDATEN
# ---------------------------------------------------------
def fetch_stock_prices():
    """Holt aktuelle Kurse ueber yfinance. Gibt Liste von dicts zurueck."""
    results = []
    try:
        import yfinance as yf
    except Exception as e:
        print(f"Warnung: yfinance nicht verfuegbar: {e}")
        return results

    for label, ticker in STOCK_TICKERS.items():
        try:
            data = yf.Ticker(ticker).history(period="2d")
            if len(data) >= 2:
                prev_close = data["Close"].iloc[-2]
                last_close = data["Close"].iloc[-1]
                change_pct = ((last_close - prev_close) / prev_close) * 100
                results.append({
                    "label": label,
                    "price": round(last_close, 2),
                    "change_pct": round(change_pct, 2),
                })
            elif len(data) == 1:
                results.append({
                    "label": label,
                    "price": round(data["Close"].iloc[-1], 2),
                    "change_pct": None,
                })
        except Exception as e:
            print(f"Warnung: Kursdaten fuer '{label}' ({ticker}) fehlgeschlagen: {e}")
    return results


# ---------------------------------------------------------
# TERMINE / HISTORISCHE EREIGNISSE + FEIERTAGE
# ---------------------------------------------------------
def fetch_on_this_day(month, day):
    """Holt 'Heute vor X Jahren'-Ereignisse von der deutschen Wikipedia."""
    url = f"https://de.wikipedia.org/api/rest_v1/feed/onthisday/events/{month}/{day}"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "morning-report-bot"})
        resp.raise_for_status()
        events = resp.json().get("events", [])
        events_sorted = sorted(events, key=lambda e: e.get("year", 0), reverse=True)
        return events_sorted[:3]
    except Exception as e:
        print(f"Warnung: 'Heute vor X Jahren' fehlgeschlagen: {e}")
        return []


def fetch_holiday_today():
    """Prueft, ob heute ein gesetzlicher Feiertag in Deutschland ist."""
    year = datetime.date.today().year
    url = f"https://date.nager.at/api/v3/publicholidays/{year}/DE"
    today_str = datetime.date.today().isoformat()
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        for holiday in resp.json():
            if holiday.get("date") == today_str:
                return holiday.get("localName")
    except Exception as e:
        print(f"Warnung: Feiertagsabfrage fehlgeschlagen: {e}")
    return None


# ---------------------------------------------------------
# ARCHIV / KALENDER
# ---------------------------------------------------------
MANIFEST_PATH = "reports/manifest.json"


def load_archive_dates():
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_archive_snapshot(today_str, html_content):
    os.makedirs("reports", exist_ok=True)
    with open(f"reports/{today_str}.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    dates = load_archive_dates()
    dates.add(today_str)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(dates), f)
    return dates


def build_calendar_html(archive_dates):
    """Baut eine einfache Monatsansicht; Tage mit Report sind anklickbar."""
    today = datetime.date.today()
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(today.year, today.month)
    weekday_labels = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

    rows = "<tr>" + "".join(f"<th>{d}</th>" for d in weekday_labels) + "</tr>\n"
    for week in weeks:
        rows += "<tr>"
        for day in week:
            if day == 0:
                rows += "<td></td>"
                continue
            date_str = f"{today.year}-{today.month:02d}-{day:02d}"
            css = "cal-day"
            if day == today.day:
                css += " cal-today"
            if date_str in archive_dates:
                rows += f'<td class="{css} cal-has"><a href="reports/{date_str}.html">{day}</a></td>'
            else:
                rows += f'<td class="{css}">{day}</td>'
        rows += "</tr>\n"

    month_name = today.strftime("%B %Y")
    return f"""<table class="calendar">
      <caption>{month_name}</caption>
      {rows}
    </table>"""


# ---------------------------------------------------------
# HTML ZUSAMMENBAUEN
# ---------------------------------------------------------
def build_stock_table(stocks):
    if not stocks:
        return "<p class=\"muted\">Kursdaten aktuell nicht verfuegbar.</p>"

    movers = [s for s in stocks if s["change_pct"] is not None]
    biggest_mover = max(movers, key=lambda s: abs(s["change_pct"])) if movers else None

    callout = ""
    if biggest_mover:
        direction = "stark gestiegen" if biggest_mover["change_pct"] >= 0 else "stark gefallen"
        callout = (
            f'<p class="mover-callout">\U0001F525 Groesste Bewegung heute: '
            f'<strong>{html.escape(biggest_mover["label"])}</strong> ist {direction} '
            f'({biggest_mover["change_pct"]}%)</p>'
        )

    rows = ""
    for s in stocks:
        if s["change_pct"] is None:
            change_html = "<span class=\"muted\">-</span>"
        else:
            arrow = "\u25B2" if s["change_pct"] >= 0 else "\u25BC"
            css = "up" if s["change_pct"] >= 0 else "down"
            change_html = f'<span class="{css}">{arrow} {s["change_pct"]}%</span>'
        row_css = " class=\"mover-row\"" if biggest_mover and s is biggest_mover else ""
        rows += f"<tr{row_css}><td>{html.escape(s['label'])}</td><td>{s['price']}</td><td>{change_html}</td></tr>\n"

    return f"""{callout}
    <table class="stocks">
      <tr><th>Wert</th><th>Kurs</th><th>Veraenderung</th></tr>
      {rows}
    </table>
    <p class="disclaimer">Keine Anlageberatung - rein informativ.</p>"""


def write_html(sections, stocks, wissen_thema, archive_dates, holiday_name=None):
    today = datetime.date.today()
    today_str = today.isoformat()
    today_display = today.strftime("%A, %d.%m.%Y")

    category_cards = ""
    for category in CATEGORY_FEEDS.keys():
        meta = CATEGORY_META[category]
        content = sections.get(category, "- Keine Daten verfuegbar")
        category_cards += f"""
        <div class="card" style="border-top-color:{meta['color']}">
          <h2><span class="icon">{meta['icon']}</span>{html.escape(category)}</h2>
          {render_bullets(content)}
        </div>"""

    wissen_label, wissen_icon, _ = wissen_thema
    wissen_content = sections.get("Wissen des Tages", "- Kein Fakt verfuegbar")
    wissen_card = f"""
        <div class="card" style="border-top-color:#f59e0b">
          <h2><span class="icon">{wissen_icon}</span>Wissen des Tages: {html.escape(wissen_label)}</h2>
          {render_bullets(wissen_content)}
        </div>"""

    stock_card = f"""
        <div class="card" style="border-top-color:#1e40af">
          <h2><span class="icon">\U0001F4C8</span>Marktdaten</h2>
          {build_stock_table(stocks)}
        </div>"""

    besonderer_content = sections.get("Besonderer Tag heute", "- Kein besonderer Anlass bekannt")
    events_card = f"""
        <div class="card" style="border-top-color:#64748b">
          <h2><span class="icon">\U0001F4C5</span>Besonderer Tag heute</h2>
          {render_bullets(besonderer_content)}
        </div>"""

    calendar_card = f"""
        <div class="card">
          <h2><span class="icon">\U0001F5D3\uFE0F</span>Archiv</h2>
          {build_calendar_html(archive_dates)}
        </div>"""

    holiday_banner = ""
    if holiday_name:
        holiday_banner = f'<div class="holiday-banner">\U0001F389 Heute ist Feiertag: {html.escape(holiday_name)}</div>'

    html_content = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>Morning Report - {today_display}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    max-width: 820px;
    margin: 0 auto;
    padding: 0 20px 60px;
    background: #f4f5f7;
    color: #1f2430;
    line-height: 1.55;
  }}
  header {{
    background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%);
    color: white;
    margin: 0 -20px 24px;
    padding: 34px 24px 26px;
    border-radius: 0 0 20px 20px;
  }}
  header h1 {{ margin: 0 0 4px; font-size: 1.5em; letter-spacing: -0.01em; }}
  header .date {{ opacity: 0.85; font-size: 0.95em; text-transform: capitalize; }}
  .holiday-banner {{
    background: #fef3c7; color: #92400e; padding: 10px 16px; border-radius: 10px;
    margin-bottom: 18px; font-size: 0.9em; font-weight: 600;
  }}
  .grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
  @media (min-width: 640px) {{ .grid.two-col {{ grid-template-columns: 1fr 1fr; }} }}
  .card {{
    background: white; padding: 20px 22px; border-radius: 14px;
    box-shadow: 0 1px 3px rgba(15,23,42,0.07); border-top: 4px solid #94a3b8;
  }}
  .card h2 {{ margin: 0 0 12px; font-size: 1.02em; display: flex; align-items: center; gap: 8px; }}
  .icon {{ font-size: 1.1em; }}
  .card ul {{ padding-left: 18px; margin: 0; }}
  .card li {{ margin-bottom: 7px; font-size: 0.94em; }}
  .card a {{ color: #1e40af; text-decoration: none; font-weight: 600; }}
  .card a:hover {{ text-decoration: underline; }}
  .muted {{ color: #94a3b8; font-size: 0.9em; }}
  table.stocks {{ width: 100%; border-collapse: collapse; font-size: 0.92em; }}
  table.stocks th {{ text-align: left; color: #64748b; font-weight: 600; padding: 4px 0; border-bottom: 1px solid #eef0f3; }}
  table.stocks td {{ padding: 6px 0; border-bottom: 1px solid #f5f6f8; }}
  .up {{ color: #16a34a; font-weight: 600; }}
  .down {{ color: #dc2626; font-weight: 600; }}
  .mover-callout {{
    background: #fff7ed; color: #9a3412; padding: 8px 12px; border-radius: 8px;
    font-size: 0.85em; margin: 0 0 10px;
  }}
  tr.mover-row {{ background: #fff7ed; }}
  .disclaimer {{ font-size: 0.75em; color: #94a3b8; margin-top: 8px; }}
  table.calendar {{ width: 100%; border-collapse: collapse; text-align: center; font-size: 0.85em; }}
  table.calendar caption {{ font-weight: 600; margin-bottom: 8px; text-transform: capitalize; }}
  table.calendar th {{ color: #94a3b8; font-weight: 500; padding: 4px; }}
  table.calendar td {{ padding: 6px 4px; border-radius: 6px; }}
  table.calendar td.cal-has a {{ color: white; background: #1e40af; border-radius: 6px; padding: 4px 7px; text-decoration: none; }}
  table.calendar td.cal-today {{ outline: 2px solid #f59e0b; }}
  footer {{ text-align: center; color: #94a3b8; font-size: 0.8em; margin-top: 24px; }}
</style>
</head>
<body>
  <header>
    <h1>Morning Intelligence Report</h1>
    <div class="date">{today_display}</div>
  </header>
  {holiday_banner}
  <div class="grid">
    {stock_card}
    {category_cards}
    {wissen_card}
    {events_card}
    {calendar_card}
  </div>
  <footer>Automatisch erstellt &middot; wird jeden Morgen aktualisiert</footer>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    save_archive_snapshot(today_str, html_content)


def main():
    items_by_category = collect_by_category()
    total_items = sum(len(v) for v in items_by_category.values())
    if total_items == 0:
        print("Keine Feed-Eintraege gefunden - breche ab, index.html wird nicht veraendert.")
        return

    day_of_year = datetime.date.today().timetuple().tm_yday
    wissen_thema = WISSEN_THEMEN[day_of_year % len(WISSEN_THEMEN)]

    today = datetime.date.today()
    today_display = today.strftime("%A, %d.%m.%Y")
    on_this_day = fetch_on_this_day(today.month, today.day)
    holiday_name = fetch_holiday_today()

    prompt = build_prompt(items_by_category, wissen_thema, on_this_day, holiday_name, today_display)
    raw_response = get_summary(prompt)
    sections = parse_categorized_response(raw_response)

    stocks = fetch_stock_prices()
    archive_dates = load_archive_dates()

    write_html(sections, stocks, wissen_thema, archive_dates, holiday_name)
    print("index.html und Archiv-Snapshot erfolgreich erstellt.")


if __name__ == "__main__":
    main()
