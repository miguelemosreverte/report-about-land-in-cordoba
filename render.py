#!/usr/bin/env python3
"""
Markdown → Static HTML renderer.

Features:
  - Wall Street Journal–inspired typography and layout
  - Tailwind CSS (CDN)
  - Custom ```chart directive → Chart.js canvases
  - Local image embedding
  - Responsive tables
  - Print-friendly
"""

import json, re, sys, os, uuid
from html import escape

INPUT = sys.argv[1] if len(sys.argv) > 1 else "report.md"
OUTPUT = os.path.splitext(INPUT)[0] + ".html"

# ---------------------------------------------------------------------------
# Markdown parser (block-level → HTML with Tailwind classes)
# ---------------------------------------------------------------------------

class Renderer:
    def __init__(self):
        self.charts: list[dict] = []  # collected chart configs
        self.chart_counter = 0

    # ── inline formatting ──
    def inline(self, text: str) -> str:
        # images — detect if inside a table cell (small thumb) or standalone
        text = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)",
            self._img_replace,
            text,
        )
        # links
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r'<a href="\2" target="_blank" class="text-wsj-blue hover:underline">\1</a>',
            text,
        )
        # bold
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # italic
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
        # inline code
        text = re.sub(r"`([^`]+)`", r'<code class="bg-gray-100 px-1 rounded text-sm">\1</code>', text)
        return text

    def _img_replace(self, m):
        alt, src = m.group(1), m.group(2)
        # Check if the image file actually exists
        if not os.path.exists(src):
            return f'<span class="text-gray-400 text-xs">sin imagen</span>'
        return (
            f'<img src="{src}" alt="{escape(alt)}" loading="lazy" '
            f'class="rounded shadow-sm object-cover" '
            f'onerror="this.style.display=\'none\'" />'
        )

    # ── block parsing ──
    def render(self, md: str) -> str:
        lines = md.split("\n")
        html_parts = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # chart code block
            if line.strip() == "```chart":
                json_lines = []
                i += 1
                while i < len(lines) and lines[i].strip() != "```":
                    json_lines.append(lines[i])
                    i += 1
                i += 1  # skip closing ```
                try:
                    config = json.loads("\n".join(json_lines))
                    html_parts.append(self._chart(config))
                except json.JSONDecodeError as e:
                    html_parts.append(f'<pre class="text-red-500">Chart JSON error: {e}</pre>')
                continue

            # other code blocks
            if line.strip().startswith("```"):
                lang = line.strip().lstrip("`").strip()
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1
                code = escape("\n".join(code_lines))
                html_parts.append(
                    f'<pre class="bg-gray-50 border border-gray-200 rounded p-4 '
                    f'overflow-x-auto text-sm font-mono my-4"><code>{code}</code></pre>'
                )
                continue

            # horizontal rule
            if re.match(r"^-{3,}\s*$", line):
                html_parts.append(
                    '<hr class="my-10 border-t border-gray-300" />'
                )
                i += 1
                continue

            # headers
            hm = re.match(r"^(#{1,6})\s+(.+)$", line)
            if hm:
                level = len(hm.group(1))
                text = self.inline(hm.group(2))
                styles = {
                    1: "text-4xl font-serif font-bold tracking-tight mt-8 mb-4 text-gray-900 border-b-2 border-gray-900 pb-3",
                    2: "text-2xl font-serif font-bold mt-10 mb-4 text-gray-900 border-b border-gray-200 pb-2",
                    3: "text-xl font-serif font-semibold mt-8 mb-3 text-gray-800",
                    4: "text-lg font-semibold mt-6 mb-2 text-gray-800",
                    5: "text-base font-semibold mt-4 mb-1 text-gray-700",
                    6: "text-sm font-semibold uppercase tracking-wide mt-4 mb-1 text-gray-500",
                }
                cls = styles.get(level, styles[6])
                html_parts.append(f"<h{level} class=\"{cls}\">{text}</h{level}>")
                i += 1
                continue

            # blockquote
            if line.startswith(">"):
                bq_lines = []
                while i < len(lines) and lines[i].startswith(">"):
                    bq_lines.append(lines[i].lstrip("> "))
                    i += 1
                inner = self.inline(" ".join(bq_lines))
                html_parts.append(
                    f'<blockquote class="border-l-4 border-wsj-blue pl-4 py-2 my-6 '
                    f'text-gray-600 italic font-serif">{inner}</blockquote>'
                )
                continue

            # table
            if "|" in line and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|", lines[i + 1]):
                table_lines = []
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i])
                    i += 1
                html_parts.append(self._table(table_lines))
                continue

            # unordered list
            if re.match(r"^[-*]\s+", line):
                items = []
                while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                    items.append(re.sub(r"^[-*]\s+", "", lines[i]))
                    i += 1
                li = "".join(
                    f'<li class="mb-1">{self.inline(it)}</li>' for it in items
                )
                html_parts.append(
                    f'<ul class="list-disc list-inside my-3 text-gray-700 space-y-1">{li}</ul>'
                )
                continue

            # ordered list
            if re.match(r"^\d+\.\s+", line):
                items = []
                while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                    items.append(re.sub(r"^\d+\.\s+", "", lines[i]))
                    i += 1
                li = "".join(
                    f'<li class="mb-1">{self.inline(it)}</li>' for it in items
                )
                html_parts.append(
                    f'<ol class="list-decimal list-inside my-3 text-gray-700 space-y-1">{li}</ol>'
                )
                continue

            # blank line
            if not line.strip():
                i += 1
                continue

            # paragraph (collect contiguous non-blank, non-special lines)
            para = []
            while (i < len(lines)
                   and lines[i].strip()
                   and not lines[i].startswith("#")
                   and not lines[i].startswith(">")
                   and not lines[i].startswith("```")
                   and not re.match(r"^[-*]\s+", lines[i])
                   and not re.match(r"^\d+\.\s+", lines[i])
                   and not re.match(r"^-{3,}\s*$", lines[i])
                   and "|" not in lines[i]):
                para.append(lines[i])
                i += 1
            if para:
                text = self.inline(" ".join(para))
                html_parts.append(
                    f'<p class="my-3 text-gray-700 leading-relaxed font-serif">{text}</p>'
                )
                continue

            # fallback: treat as paragraph
            html_parts.append(
                f'<p class="my-3 text-gray-700 leading-relaxed font-serif">{self.inline(line)}</p>'
            )
            i += 1

        return "\n".join(html_parts)

    # ── table renderer ──
    def _table(self, lines):
        # Check if this table has images (listing table)
        has_images = any("![" in l for l in lines)

        rows = []
        for line in lines:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)

        if len(rows) < 2:
            return ""

        header = rows[0]
        # skip separator row (row 1)
        body = rows[2:] if len(rows) > 2 else []

        # Determine alignment from separator
        sep = rows[1] if len(rows) > 1 else []
        aligns = []
        for s in sep:
            s = s.strip()
            if s.startswith(":") and s.endswith(":"):
                aligns.append("center")
            elif s.endswith(":"):
                aligns.append("right")
            else:
                aligns.append("left")

        def align_class(idx):
            if idx < len(aligns):
                a = aligns[idx]
                if a == "right":
                    return " text-right"
                if a == "center":
                    return " text-center"
            return " text-left"

        # Choose style based on table type
        if has_images:
            return self._listing_cards(header, body, aligns)

        # Regular table
        ths = "".join(
            f'<th class="px-3 py-2 text-left text-xs font-semibold uppercase '
            f'tracking-wider text-gray-500 bg-gray-50 border-b-2 border-gray-300'
            f'{align_class(i)}">{self.inline(h)}</th>'
            for i, h in enumerate(header)
        )
        trs = []
        for ri, row in enumerate(body):
            tds = "".join(
                f'<td class="px-3 py-2 text-sm text-gray-700 border-b border-gray-100'
                f'{align_class(ci)} whitespace-nowrap">{self.inline(c)}</td>'
                for ci, c in enumerate(row)
            )
            stripe = ' class="bg-gray-50/50"' if ri % 2 else ""
            trs.append(f"<tr{stripe}>{tds}</tr>")

        return (
            '<div class="overflow-x-auto my-6 rounded border border-gray-200 shadow-sm">'
            '<table class="min-w-full divide-y divide-gray-200 text-sm">'
            f"<thead><tr>{ths}</tr></thead>"
            f'<tbody class="divide-y divide-gray-100">{"".join(trs)}</tbody>'
            "</table></div>"
        )

    def _listing_cards(self, header, body, aligns):
        """Render image-containing tables as a responsive card grid."""
        cards = []
        for row in body:
            # Parse columns: | # | Imagen | Ubicación | Superficie | Precio | Precio/m² | Link |
            num = row[0].strip() if len(row) > 0 else ""
            img_html = self.inline(row[1]) if len(row) > 1 else ""
            location = self.inline(row[2]) if len(row) > 2 else ""
            size = self.inline(row[3]) if len(row) > 3 else ""
            price = self.inline(row[4]) if len(row) > 4 else ""
            ppm = self.inline(row[5]) if len(row) > 5 else ""
            link = self.inline(row[6]) if len(row) > 6 else ""

            card = f'''
            <div class="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden
                        hover:shadow-md transition-shadow duration-200">
                <div class="aspect-[16/10] overflow-hidden bg-gray-100 flex items-center justify-center">
                    {img_html if img_html and "sin imagen" not in img_html
                     else '<div class="text-gray-300 text-sm">Sin imagen</div>'}
                </div>
                <div class="p-4">
                    <div class="flex items-baseline justify-between mb-1">
                        <span class="text-xs text-gray-400 font-mono">#{num}</span>
                        <span class="text-xs font-semibold text-wsj-blue">{ppm}</span>
                    </div>
                    <h4 class="font-serif font-semibold text-gray-900 text-sm mb-2 leading-tight">{location}</h4>
                    <div class="flex justify-between items-center text-sm">
                        <span class="text-gray-600">{size}</span>
                        <span class="font-bold text-gray-900">{price}</span>
                    </div>
                    <div class="mt-3 text-right">{link}</div>
                </div>
            </div>'''
            cards.append(card)

        return (
            f'<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 my-6">'
            f'{"".join(cards)}'
            f'</div>'
        )

    # ── chart renderer ──
    def _chart(self, config: dict) -> str:
        cid = f"chart_{self.chart_counter}"
        self.chart_counter += 1
        self.charts.append({"id": cid, "config": config})

        h = "h-80" if config.get("type") != "scatter" else "h-96"
        return (
            f'<div class="my-8 bg-white border border-gray-200 rounded-lg shadow-sm p-4">'
            f'<div class="{h}"><canvas id="{cid}"></canvas></div>'
            f'</div>'
        )


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

def html_page(body: str, charts: list[dict], title="Terrenos en Córdoba") -> str:
    chart_scripts = "\n".join(
        f'new Chart(document.getElementById("{c["id"]}"), {json.dumps(c["config"], ensure_ascii=False)});'
        for c in charts
    )

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{escape(title)}</title>

<!-- Tailwind CSS -->
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {{
  theme: {{
    extend: {{
      colors: {{
        'wsj-blue': '#0274B6',
        'wsj-dark': '#111111',
        'wsj-cream': '#FFF9F0',
      }},
      fontFamily: {{
        serif: ['Georgia', 'Charter', '"Times New Roman"', 'serif'],
        sans: ['"Helvetica Neue"', 'Arial', 'sans-serif'],
      }},
    }},
  }},
}}
</script>

<!-- Chart.js -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>

<style>
  @media print {{
    .no-print {{ display: none !important; }}
    body {{ font-size: 11pt; }}
  }}
  /* WSJ-style refinements */
  body {{ -webkit-font-smoothing: antialiased; }}
  table img {{
    width: 100%;
    height: auto;
    max-height: 160px;
    object-fit: cover;
  }}
  .listing-card img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
  /* Chart.js defaults */
  canvas {{ max-width: 100%; }}
  /* Responsive card images */
  .aspect-\\[16\\/10\\] img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
</style>
</head>

<body class="bg-wsj-cream min-h-screen">

<!-- Navigation bar -->
<nav class="bg-wsj-dark text-white py-3 px-6 sticky top-0 z-50 shadow-md no-print">
  <div class="max-w-6xl mx-auto flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="border-r border-gray-600 pr-3">
        <span class="font-serif text-xl font-bold tracking-tight">TERRENOS</span>
      </div>
      <span class="text-gray-400 text-sm font-sans">Córdoba · Reporte de Mercado</span>
    </div>
    <div class="text-gray-400 text-xs font-sans">
      Fuente: zonaprop.com.ar
    </div>
  </div>
</nav>

<!-- Main content -->
<main class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
  <article class="bg-white shadow-sm rounded-lg border border-gray-200 px-6 sm:px-10 lg:px-14 py-10">
    {body}
  </article>

  <footer class="text-center text-gray-400 text-xs py-8 font-sans">
    Reporte generado automáticamente · Datos de ZonaProp · {title}
  </footer>
</main>

<!-- Chart initialization -->
<script>
document.addEventListener("DOMContentLoaded", function() {{
  Chart.defaults.font.family = "'Helvetica Neue', Arial, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = "#555";
  Chart.defaults.plugins.legend.display = false;

  {chart_scripts}
}});
</script>

</body>
</html>'''


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not os.path.exists(INPUT):
        print(f"Error: {INPUT} not found.")
        sys.exit(1)

    with open(INPUT, "r", encoding="utf-8") as f:
        md = f.read()

    r = Renderer()
    body = r.render(md)
    html = html_page(body, r.charts)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Rendered: {INPUT} → {OUTPUT}")
    print(f"  Charts: {len(r.charts)}")
    print(f"  Size: {len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
