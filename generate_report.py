"""
Morning Intelligence Report Generator
--------------------------------------
Liest RSS-Feeds aus, laesst Gemini eine Zusammenfassung erstellen
und schreibt das Ergebnis als index.html (fuer GitHub Pages).
"""

import os
import html
import datetime
import feedparser
from google import genai

# ---------------------------------------------------------
# 1. HIER DEINE QUELLEN EINTRAGEN (RSS-Feeds)
#    Einfach weitere Zeilen hinzufuegen oder entfernen.
# ---------------------------------------------------------
FEEDS = {
    "arXiv - KI Papers": "http://export.arxiv.org/rss/cs.AI",
    "Heise Online - Tech & KI": "https://www.heise.de/newsticker/heise.rdf",
    "Tagesschau - Wirtschaft": "https://www.tagesschau.de/wirtschaft/index~rss2.xml",
    "Handelsblatt": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen",
    "Wissenschaft.de": "https://www.wissenschaft.de/feed/",
}

MAX_ITEMS_PER_FEED = 5


def collect_headlines():
    """Holt die neuesten Eintraege aus allen konfigurierten Feeds."""
    all_items = []
    for source_name, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                all_items.append({
                    "source": source_name,
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "link": entry.get("link", ""),
                })
        except Exception as e:
            print(f"Warnung: Feed '{source_name}' konnte nicht geladen werden: {e}")
    return all_items


def build_prompt(items):
    """Baut den Prompt fuer Gemini aus den gesammelten Schlagzeilen."""
    text_block = ""
    for item in items:
        clean_summary = item["summary"].replace("\n", " ")[:200]
        text_block += f"- [{item['source']}] {item['title']}: {clean_summary}\n"

    prompt = f"""Du bist ein persoenlicher Nachrichtenassistent.
Hier ist eine Liste aktueller Schlagzeilen aus verschiedenen Quellen:

{text_block}

Erstelle daraus einen kurzen, gut strukturierten Morgenbericht auf Deutsch mit:
1. Einer Executive Summary (3-4 Saetze, die wichtigsten Erkenntnisse)
2. Den 5-8 wichtigsten Einzelmeldungen mit einer kurzen Erklaerung, warum sie relevant sind
3. Thematischer Gruppierung, wenn sinnvoll

Formatiere die Antwort in Markdown (Ueberschriften mit ##, Listen mit -)."""
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


def markdown_to_simple_html(markdown_text):
    """Sehr einfache Markdown-zu-HTML Umwandlung (keine externe Bibliothek noetig)."""
    lines = markdown_text.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{html.escape(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{html.escape(stripped[2:])}</h2>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{html.escape(stripped[2:])}</li>")
        elif stripped == "":
            if in_list:
                html_lines.append("</ul>")
                in_list = False
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{html.escape(stripped)}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def write_html(summary_text, items):
    """Schreibt den fertigen Report als index.html."""
    today = datetime.date.today().strftime("%A, %d.%m.%Y")
    html_body = markdown_to_simple_html(summary_text)

    sources_html = ""
    for item in items:
        safe_title = html.escape(item["title"])
        sources_html += (
            f'<li><a href="{item["link"]}" target="_blank">{safe_title}</a> '
            f'<span class="source">{item["source"]}</span></li>\n'
        )

    html_content = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morning Report - {today}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    max-width: 760px;
    margin: 0 auto;
    padding: 0 20px 60px;
    background: #f4f5f7;
    color: #1f2430;
    line-height: 1.6;
  }}
  header {{
    background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%);
    color: white;
    margin: 0 -20px 28px;
    padding: 36px 24px 28px;
    border-radius: 0 0 20px 20px;
  }}
  header h1 {{ margin: 0 0 4px; font-size: 1.5em; letter-spacing: -0.01em; }}
  header .date {{ opacity: 0.85; font-size: 0.95em; text-transform: capitalize; }}
  h2 {{ color: #1e293b; margin: 0 0 14px; font-size: 1.05em; border-left: 4px solid #1e40af; padding-left: 10px; }}
  .report {{ background: white; padding: 26px 28px; border-radius: 14px; box-shadow: 0 1px 3px rgba(15,23,42,0.06); margin-bottom: 20px; }}
  .report h2:not(:first-child) {{ margin-top: 26px; }}
  .report ul {{ padding-left: 20px; margin: 0 0 4px; }}
  .report li {{ margin-bottom: 8px; }}
  .report p {{ margin: 0 0 12px; }}
  .sources {{ background: white; padding: 22px 28px; border-radius: 14px; box-shadow: 0 1px 3px rgba(15,23,42,0.06); }}
  .sources ul {{ list-style: none; padding: 0; margin: 0; }}
  .sources li {{ padding: 10px 0; border-bottom: 1px solid #eef0f3; display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
  .sources li:last-child {{ border-bottom: none; }}
  .source {{ color: #94a3b8; font-size: 0.8em; white-space: nowrap; background: #f1f5f9; padding: 2px 8px; border-radius: 6px; }}
  a {{ color: #1e40af; text-decoration: none; font-weight: 500; }}
  a:hover {{ text-decoration: underline; }}
  footer {{ text-align: center; color: #94a3b8; font-size: 0.8em; margin-top: 24px; }}
</style>
</head>
<body>
  <header>
    <h1>Morning Intelligence Report</h1>
    <div class="date">{today}</div>
  </header>
  <div class="report">
    {html_body}
  </div>
  <div class="sources">
    <h2>Quellen</h2>
    <ul>
      {sources_html}
    </ul>
  </div>
  <footer>Automatisch erstellt &middot; wird jeden Morgen aktualisiert</footer>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    return html_content


def send_email(html_content, today):
    """Verschickt den Report per E-Mail ueber Gmail SMTP (kostenlos, App-Passwort noetig)."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    sender = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not sender or not app_password:
        print("Kein GMAIL_ADDRESS/GMAIL_APP_PASSWORD gesetzt - E-Mail-Versand wird uebersprungen.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Morning Report - {today}"
    msg["From"] = sender
    msg["To"] = sender
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, sender, msg.as_string())
        print("E-Mail erfolgreich versendet.")
    except Exception as e:
        print(f"Warnung: E-Mail-Versand fehlgeschlagen: {e}")


def main():
    items = collect_headlines()
    if not items:
        print("Keine Feed-Eintraege gefunden - breche ab, index.html wird nicht veraendert.")
        return
    prompt = build_prompt(items)
    summary = get_summary(prompt)
    html_content = write_html(summary, items)
    today = datetime.date.today().strftime("%A, %d.%m.%Y")
    send_email(html_content, today)
    print("index.html erfolgreich erstellt.")


if __name__ == "__main__":
    main()
