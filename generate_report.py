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
import google.generativeai as genai

# ---------------------------------------------------------
# 1. HIER DEINE QUELLEN EINTRAGEN (RSS-Feeds)
#    Einfach weitere Zeilen hinzufuegen oder entfernen.
# ---------------------------------------------------------
FEEDS = {
    "arXiv - KI Papers": "http://export.arxiv.org/rss/cs.AI",
    "Hacker News": "https://hnrss.org/frontpage",
    "Tagesschau": "https://www.tagesschau.de/xml/rss2/",
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
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
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
    today = datetime.date.today().strftime("%d.%m.%Y")
    html_body = markdown_to_simple_html(summary_text)

    sources_html = ""
    for item in items:
        safe_title = html.escape(item["title"])
        sources_html += (
            f'<li><a href="{item["link"]}" target="_blank">{safe_title}</a> '
            f'<span class="source">({item["source"]})</span></li>\n'
        )

    html_content = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morning Report - {today}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    max-width: 800px;
    margin: 40px auto;
    padding: 0 20px;
    background: #f5f6f8;
    color: #1a1a1a;
    line-height: 1.5;
  }}
  h1 {{ color: #1e3a8a; margin-bottom: 4px; }}
  h2 {{ color: #1e3a8a; margin-top: 28px; font-size: 1.2em; }}
  .date {{ color: #666; margin-bottom: 30px; font-size: 0.95em; }}
  .report {{ background: white; padding: 30px; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
  .report ul {{ padding-left: 20px; }}
  .report li {{ margin-bottom: 6px; }}
  .sources {{ margin-top: 24px; background: white; padding: 20px 30px; border-radius: 12px; }}
  .sources ul {{ padding-left: 20px; }}
  .sources li {{ margin-bottom: 8px; }}
  .source {{ color: #888; font-size: 0.85em; }}
  a {{ color: #1e40af; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
  <h1>Morning Intelligence Report</h1>
  <div class="date">{today}</div>
  <div class="report">
    {html_body}
  </div>
  <div class="sources">
    <h2>Quellen</h2>
    <ul>
      {sources_html}
    </ul>
  </div>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)


def main():
    items = collect_headlines()
    if not items:
        print("Keine Feed-Eintraege gefunden - breche ab, index.html wird nicht veraendert.")
        return
    prompt = build_prompt(items)
    summary = get_summary(prompt)
    write_html(summary, items)
    print("index.html erfolgreich erstellt.")


if __name__ == "__main__":
    main()
