#!/usr/bin/env python3
"""
Markdown + data.json → Static HTML renderer.

Features:
  - WSJ-style typography (Tailwind CSS CDN)
  - Leaflet.js interactive map with sticky scroll-tracking
  - Chart.js charts via ```chart directives
  - Arsenic / water safety section from arsenic_risk_data.json
  - Lake contamination notes (San Roque, Los Molinos)
  - Responsive card grid with downloaded images
  - Print-friendly
"""

import json, re, sys, os
from html import escape

INPUT_MD = sys.argv[1] if len(sys.argv) > 1 else "report.md"
DATA_FILE = "data.json"
ARSENIC_FILE = "arsenic_risk_data.json"
OUTPUT = "index.html"

# ── Load data ──

listings_data = []
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        listings_data = json.load(f)

arsenic_data = {}
if os.path.exists(ARSENIC_FILE):
    with open(ARSENIC_FILE, "r", encoding="utf-8") as f:
        arsenic_data = json.load(f)


# ── Arsenic risk lookup ──

def build_arsenic_lookup():
    """Build a flat lookup: location_name → {risk, range, notes}."""
    lookup = {}
    table = arsenic_data.get("risk_summary_table", [])
    for entry in table:
        loc = entry.get("location", "")
        lookup[loc] = {
            "risk": entry.get("risk", "unknown"),
            "range": entry.get("As_range_ug_L", "—"),
            "safe": entry.get("municipal_water_safe", "unknown"),
        }
    return lookup

arsenic_lookup = build_arsenic_lookup()


def get_arsenic_risk(location_str):
    """Get arsenic risk for a location string."""
    name = location_str.split(",")[0].strip()
    # Direct match
    if name in arsenic_lookup:
        return arsenic_lookup[name]
    # Try partial matches
    for key, val in arsenic_lookup.items():
        if name.lower() in key.lower() or key.lower() in name.lower():
            return val
    # Default based on Córdoba city neighborhoods
    if "Córdoba" in location_str:
        return {"risk": "low", "range": "<10", "safe": True}
    return {"risk": "unknown", "range": "—", "safe": "unknown"}


# ── Markdown Renderer ──

class Renderer:
    def __init__(self):
        self.charts = []
        self.chart_counter = 0

    def inline(self, text):
        # images
        text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", self._img_replace, text)
        # links
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r'<a href="\2" target="_blank" rel="noopener" '
            r'class="text-wsj-blue hover:underline">\1</a>',
            text,
        )
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(r"`([^`]+)`",
                       r'<code class="bg-gray-100 px-1 rounded text-xs">\1</code>', text)
        return text

    def _img_replace(self, m):
        alt, src = m.group(1), m.group(2)
        if not os.path.exists(src):
            return '<span class="text-gray-400 text-xs">sin imagen</span>'
        return (f'<img src="{src}" alt="{escape(alt)}" loading="lazy" '
                f'class="rounded shadow-sm object-cover" '
                f'onerror="this.style.display=\'none\'" />')

    def render(self, md):
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
                i += 1
                try:
                    config = json.loads("\n".join(json_lines))
                    html_parts.append(self._chart(config))
                except json.JSONDecodeError as e:
                    html_parts.append(f'<pre class="text-red-500">Chart error: {e}</pre>')
                continue

            if line.strip().startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1
                code = escape("\n".join(code_lines))
                html_parts.append(
                    f'<pre class="bg-gray-50 border rounded p-4 overflow-x-auto text-sm font-mono my-4">'
                    f'<code>{code}</code></pre>')
                continue

            if re.match(r"^-{3,}\s*$", line):
                html_parts.append('<hr class="my-10 border-t border-gray-300" />')
                i += 1
                continue

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
                html_parts.append(f'<h{level} class="{cls}">{text}</h{level}>')
                i += 1
                continue

            if line.startswith(">"):
                bq = []
                while i < len(lines) and lines[i].startswith(">"):
                    bq.append(lines[i].lstrip("> "))
                    i += 1
                inner = self.inline(" ".join(bq))
                html_parts.append(
                    f'<blockquote class="border-l-4 border-wsj-blue pl-4 py-2 my-6 '
                    f'text-gray-600 italic font-serif">{inner}</blockquote>')
                continue

            if "|" in line and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|", lines[i + 1]):
                table_lines = []
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i])
                    i += 1
                has_images = any("![" in l for l in table_lines)
                if has_images:
                    html_parts.append(self._listing_cards(table_lines))
                else:
                    html_parts.append(self._table(table_lines))
                continue

            if re.match(r"^[-*]\s+", line):
                items = []
                while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                    items.append(re.sub(r"^[-*]\s+", "", lines[i]))
                    i += 1
                li = "".join(f'<li class="mb-1">{self.inline(it)}</li>' for it in items)
                html_parts.append(f'<ul class="list-disc list-inside my-3 text-gray-700 space-y-1">{li}</ul>')
                continue

            if re.match(r"^\d+\.\s+", line):
                items = []
                while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                    items.append(re.sub(r"^\d+\.\s+", "", lines[i]))
                    i += 1
                li = "".join(f'<li class="mb-1">{self.inline(it)}</li>' for it in items)
                html_parts.append(f'<ol class="list-decimal list-inside my-3 text-gray-700 space-y-1">{li}</ol>')
                continue

            if not line.strip():
                i += 1
                continue

            para = []
            while (i < len(lines) and lines[i].strip()
                   and not lines[i].startswith("#") and not lines[i].startswith(">")
                   and not lines[i].startswith("```")
                   and not re.match(r"^[-*]\s+", lines[i])
                   and not re.match(r"^\d+\.\s+", lines[i])
                   and not re.match(r"^-{3,}\s*$", lines[i])
                   and "|" not in lines[i]):
                para.append(lines[i])
                i += 1
            if para:
                text = self.inline(" ".join(para))
                html_parts.append(f'<p class="my-3 text-gray-700 leading-relaxed font-serif">{text}</p>')
                continue

            html_parts.append(f'<p class="my-3 text-gray-700 leading-relaxed font-serif">{self.inline(line)}</p>')
            i += 1

        return "\n".join(html_parts)

    def _table(self, lines):
        rows = []
        for line in lines:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
        if len(rows) < 2:
            return ""
        header = rows[0]
        sep = rows[1] if len(rows) > 1 else []
        body = rows[2:] if len(rows) > 2 else []
        aligns = []
        for s in sep:
            s = s.strip()
            if s.startswith(":") and s.endswith(":"):
                aligns.append("center")
            elif s.endswith(":"):
                aligns.append("right")
            else:
                aligns.append("left")

        def acls(idx):
            if idx < len(aligns):
                a = aligns[idx]
                if a == "right": return " text-right"
                if a == "center": return " text-center"
            return " text-left"

        ths = "".join(
            f'<th class="px-3 py-2 text-xs font-semibold uppercase tracking-wider '
            f'text-gray-500 bg-gray-50 border-b-2 border-gray-300{acls(i)}">'
            f'{self.inline(h)}</th>'
            for i, h in enumerate(header))
        trs = []
        for ri, row in enumerate(body):
            tds = "".join(
                f'<td class="px-3 py-2 text-sm text-gray-700 border-b border-gray-100'
                f'{acls(ci)} whitespace-nowrap">{self.inline(c)}</td>'
                for ci, c in enumerate(row))
            stripe = ' class="bg-gray-50/50"' if ri % 2 else ""
            trs.append(f"<tr{stripe}>{tds}</tr>")
        return (
            '<div class="overflow-x-auto my-6 rounded border border-gray-200 shadow-sm">'
            '<table class="min-w-full divide-y divide-gray-200 text-sm">'
            f"<thead><tr>{ths}</tr></thead>"
            f'<tbody class="divide-y divide-gray-100">{"".join(trs)}</tbody>'
            "</table></div>")

    def _listing_cards(self, lines):
        rows = []
        for line in lines:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
        if len(rows) < 3:
            return ""
        body = rows[2:]
        cards = []
        for row in body:
            num = row[0].strip() if len(row) > 0 else ""
            img_html = self.inline(row[1]) if len(row) > 1 else ""
            location = self.inline(row[2]) if len(row) > 2 else ""
            size = self.inline(row[3]) if len(row) > 3 else ""
            price = self.inline(row[4]) if len(row) > 4 else ""
            ppm = self.inline(row[5]) if len(row) > 5 else ""
            link = self.inline(row[6]) if len(row) > 6 else ""

            # Get location text for arsenic badge
            loc_text = re.sub(r"<[^>]+>", "", row[2]) if len(row) > 2 else ""
            risk = get_arsenic_risk(loc_text)
            risk_color = {"low": "green", "medium": "yellow", "medium_to_high": "red",
                          "low_to_medium": "yellow", "high": "red"}.get(risk["risk"], "gray")
            risk_badge = (
                f'<span class="inline-block px-1.5 py-0.5 text-[10px] font-semibold rounded '
                f'bg-{risk_color}-100 text-{risk_color}-800" '
                f'title="Arsénico: {risk["range"]} μg/L">💧 {risk["risk"].upper()}</span>'
            )

            card = f'''
            <div class="listing-card bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden
                        hover:shadow-md transition-shadow duration-200"
                 data-listing-num="{num}">
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
                    <div class="flex justify-between items-center text-sm mb-2">
                        <span class="text-gray-600">{size}</span>
                        <span class="font-bold text-gray-900">{price}</span>
                    </div>
                    <div class="flex justify-between items-center">
                        {risk_badge}
                        <span class="text-xs">{link}</span>
                    </div>
                </div>
            </div>'''
            cards.append(card)

        return (
            '<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 my-6">'
            f'{"".join(cards)}'
            '</div>')

    def _chart(self, config):
        cid = f"chart_{self.chart_counter}"
        self.chart_counter += 1
        self.charts.append({"id": cid, "config": config})
        h = "h-80" if config.get("type") != "scatter" else "h-96"
        return (
            f'<div class="my-8 bg-white border border-gray-200 rounded-lg shadow-sm p-4">'
            f'<div class="{h}"><canvas id="{cid}"></canvas></div></div>')


# ── Leaflet Map Data ──

def build_map_geojson():
    """Build GeoJSON from listings with coordinates."""
    features = []
    for l in listings_data:
        if not l.get("lat") or not l.get("lng"):
            continue
        risk = get_arsenic_risk(l.get("location", ""))
        props = {
            "id": l.get("id", ""),
            "location": l.get("location", ""),
            "price_text": l.get("price_text", ""),
            "price_value": l.get("price_value"),
            "size_m2": l.get("size_m2"),
            "price_per_m2": l.get("price_per_m2"),
            "link": l.get("link", ""),
            "image": l.get("image_local", ""),
            "arsenic_risk": risk["risk"],
            "arsenic_range": risk["range"],
        }
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [l["lng"], l["lat"]]},
            "properties": props,
        })
    return {"type": "FeatureCollection", "features": features}


# ── Arsenic section HTML ──

def arsenic_section_html():
    if not arsenic_data:
        return ""

    narrative = arsenic_data.get("narrative_summary", {})
    standards = arsenic_data.get("regulatory_standards", {})
    table = arsenic_data.get("risk_summary_table", [])

    who_limit = standards.get("WHO", {}).get("guideline_ug_L", 10)
    ar_limit = standards.get("Argentina", {}).get("current_standard_ug_L", 10)

    rows_html = ""
    for entry in table:
        risk = entry.get("risk", "unknown")
        color = {"low": "green", "medium": "yellow", "medium_to_high": "red",
                 "low_to_medium": "yellow", "high": "red"}.get(risk, "gray")
        safe = entry.get("municipal_water_safe", "—")
        safe_icon = "✅" if safe is True else ("⚠️" if safe == "variable" else ("🔧" if "treatment" in str(safe) else "—"))
        rows_html += f'''<tr class="border-b border-gray-100">
            <td class="px-3 py-2 text-sm">{entry.get("location", "")}</td>
            <td class="px-3 py-2 text-sm">{entry.get("zone_type", "")}</td>
            <td class="px-3 py-2 text-sm">
                <span class="px-2 py-0.5 rounded text-xs font-semibold bg-{color}-100 text-{color}-800">
                    {risk.upper().replace("_", " ")}
                </span>
            </td>
            <td class="px-3 py-2 text-sm font-mono">{entry.get("As_range_ug_L", "—")} μg/L</td>
            <td class="px-3 py-2 text-sm text-center">{safe_icon}</td>
        </tr>'''

    return f'''
    <section id="water-safety" class="mt-16">
        <h2 class="text-2xl font-serif font-bold mt-10 mb-4 text-gray-900 border-b border-gray-200 pb-2">
            Calidad del Agua: Arsénico y Contaminación de Lagos
        </h2>

        <!-- Standards -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 my-6">
            <div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <h4 class="font-semibold text-blue-900 mb-2">Estándar OMS</h4>
                <p class="text-3xl font-bold text-blue-800">{who_limit} μg/L</p>
                <p class="text-sm text-blue-600 mt-1">Límite recomendado de arsénico en agua potable</p>
            </div>
            <div class="bg-green-50 border border-green-200 rounded-lg p-4">
                <h4 class="font-semibold text-green-900 mb-2">Estándar Argentina</h4>
                <p class="text-3xl font-bold text-green-800">{ar_limit} μg/L</p>
                <p class="text-sm text-green-600 mt-1">Código Alimentario Argentino (actualizado)</p>
            </div>
        </div>

        <!-- Overview -->
        <div class="bg-gray-50 border border-gray-200 rounded-lg p-6 my-6">
            <h3 class="text-lg font-serif font-semibold mb-3">Contexto Geológico</h3>
            <p class="text-gray-700 font-serif leading-relaxed mb-4">
                {escape(narrative.get("overview", ""))}
            </p>
            <div class="bg-green-50 border-l-4 border-green-500 p-4 rounded my-4">
                <h4 class="font-semibold text-green-800 mb-1">Buenas noticias para compradores en las Sierras</h4>
                <p class="text-green-700 text-sm font-serif">
                    {escape(narrative.get("good_news_for_sierras_buyers", ""))}
                </p>
            </div>
            <div class="bg-yellow-50 border-l-4 border-yellow-500 p-4 rounded my-4">
                <h4 class="font-semibold text-yellow-800 mb-1">Zonas con precaución</h4>
                <p class="text-yellow-700 text-sm font-serif">
                    {escape(narrative.get("caution_areas", ""))}
                </p>
            </div>
        </div>

        <!-- Risk table -->
        <h3 class="text-xl font-serif font-semibold mt-8 mb-3 text-gray-800">
            Riesgo de Arsénico por Localidad
        </h3>
        <div class="overflow-x-auto my-4 rounded border border-gray-200 shadow-sm">
            <table class="min-w-full text-sm">
                <thead>
                    <tr class="bg-gray-50 border-b-2 border-gray-300">
                        <th class="px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500">Localidad</th>
                        <th class="px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500">Tipo de zona</th>
                        <th class="px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500">Riesgo</th>
                        <th class="px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500">Arsénico</th>
                        <th class="px-3 py-2 text-center text-xs font-semibold uppercase text-gray-500">Agua municipal</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>

        <!-- Lake contamination -->
        <h3 class="text-xl font-serif font-semibold mt-10 mb-3 text-gray-800">
            Contaminación de Lagos: Nota Importante
        </h3>
        <div class="bg-red-50 border border-red-200 rounded-lg p-6 my-4">
            <h4 class="font-semibold text-red-900 mb-3 text-lg">🚫 Lago San Roque (Villa Carlos Paz)</h4>
            <p class="text-red-800 text-sm font-serif mb-2">
                El Lago San Roque presenta un <strong>problema de contaminación crónico de más de 50 años</strong>.
                De las 20 localidades que vierten sus desechos al lago, la mayoría no tiene red cloacal — solo el
                ~30% de los 150.000 habitantes de la cuenca cuentan con conexión cloacal regular.
            </p>
            <p class="text-red-800 text-sm font-serif mb-2">
                Esto genera proliferación masiva de <strong>cianobacterias (Microcystis aeruginosa)</strong>,
                especialmente después de lluvias fuertes y en temporada de verano. Las toxinas pueden causar
                gastroenteritis, dolor abdominal, inflamación hepática y daño renal.
            </p>
            <p class="text-red-700 text-xs italic">
                ⚠️ No recomendado para natación en temporada alta ni después de lluvias intensas.
                El lago abastece de agua potable al 70% de la ciudad de Córdoba (tratada en planta).
            </p>
        </div>

        <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-6 my-4">
            <h4 class="font-semibold text-yellow-900 mb-3 text-lg">⚠️ Lago Los Molinos</h4>
            <p class="text-yellow-800 text-sm font-serif mb-2">
                El Lago Los Molinos presenta contaminación creciente similar al San Roque.
                <strong>No existe red cloacal en la zona</strong> (excepto Villa General Belgrano).
                Los efluentes cloacales se vierten directamente al lago sin tratamiento.
            </p>
            <p class="text-yellow-800 text-sm font-serif mb-2">
                Se ha detectado <strong>presencia de cianobacterias</strong>. El lago abastece de agua potable
                al 30% de la provincia. Deforestación, incendios y agroquímicos agravan la situación.
            </p>
            <p class="text-yellow-700 text-xs italic">
                Plan de saneamiento aprobado pero aún en ejecución (horizonte ~10 años).
            </p>
        </div>

        <!-- Practical advice -->
        <div class="bg-blue-50 border border-blue-200 rounded-lg p-6 my-6">
            <h4 class="font-semibold text-blue-900 mb-2">Consejos Prácticos para Compradores</h4>
            <ul class="list-disc list-inside text-sm text-blue-800 space-y-1 font-serif">
                <li>En localidades serranas y Córdoba capital, el arsénico <strong>no es preocupación</strong> con agua municipal.</li>
                <li>Para propiedades rurales o con pozo propio, <strong>siempre solicitar análisis de agua</strong> que incluya arsénico.</li>
                <li>En localidades de llanura (Monte Cristo, Río Segundo), el análisis de arsénico es <strong>esencial antes de la compra</strong>.</li>
                <li>Los sistemas de <strong>ósmosis inversa</strong> eliminan eficazmente el arsénico (solución domiciliaria viable).</li>
                <li>El estándar argentino de 10 μg/L coincide con la OMS; resultados superiores requieren tratamiento.</li>
            </ul>
        </div>
    </section>'''


# ── HTML Template ──

def html_page(body, charts, arsenic_html):
    geojson = build_map_geojson()
    geojson_js = json.dumps(geojson, ensure_ascii=False)

    chart_scripts = "\n".join(
        f'new Chart(document.getElementById("{c["id"]}"), {json.dumps(c["config"], ensure_ascii=False)});'
        for c in charts)

    # Lake markers for the map
    lake_markers_js = """
    // Lake contamination markers
    var sanRoque = L.circle([-31.383, -64.470], {
        color: '#dc2626', fillColor: '#fecaca', fillOpacity: 0.4, radius: 3000, weight: 2
    }).addTo(map);
    sanRoque.bindPopup('<strong>🚫 Lago San Roque</strong><br>Contaminación cloacal crónica.<br>Cianobacterias en verano y post-lluvia.<br><em>No recomendado para natación.</em>');

    var losMolinos = L.circle([-31.822, -64.537], {
        color: '#f59e0b', fillColor: '#fef3c7', fillOpacity: 0.4, radius: 2500, weight: 2
    }).addTo(map);
    losMolinos.bindPopup('<strong>⚠️ Lago Los Molinos</strong><br>Contaminación creciente, sin red cloacal.<br>Cianobacterias detectadas.<br><em>Plan de saneamiento en ejecución.</em>');
    """

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Terrenos en Córdoba — Reporte de Mercado</title>

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

<!-- Leaflet CSS & JS -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<!-- Chart.js -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>

<style>
  @media print {{
    .no-print {{ display: none !important; }}
    body {{ font-size: 11pt; }}
    #map-sidebar {{ display: none !important; }}
  }}
  body {{ -webkit-font-smoothing: antialiased; }}
  .listing-card img {{ width: 100%; height: 100%; object-fit: cover; }}
  canvas {{ max-width: 100%; }}
  .aspect-\\[16\\/10\\] img {{ width: 100%; height: 100%; object-fit: cover; }}
  #map-sidebar {{
    position: sticky;
    top: 56px;
    height: calc(100vh - 56px);
    z-index: 10;
  }}
  #map {{ height: 100%; width: 100%; }}
  .marker-active {{
    filter: hue-rotate(120deg) brightness(1.3);
    z-index: 1000 !important;
  }}
  .listing-card.active-listing {{
    outline: 4px dashed #0274B6 !important;
    outline-offset: 2px;
    box-shadow: 0 0 0 8px rgba(2, 116, 182, 0.15), 0 4px 20px rgba(2, 116, 182, 0.3) !important;
    transform: scale(1.02);
    transition: all 0.3s ease;
    z-index: 5;
    position: relative;
  }}
  @keyframes marker-pulse {{
    0% {{ opacity: 1; r: 12; }}
    50% {{ opacity: 0.4; r: 20; }}
    100% {{ opacity: 1; r: 12; }}
  }}
  @keyframes marker-blink {{
    0%, 100% {{ fill-opacity: 0.9; stroke-width: 4; }}
    50% {{ fill-opacity: 0.3; stroke-width: 2; }}
  }}
  .leaflet-marker-active {{
    animation: marker-blink 0.8s ease-in-out infinite;
  }}
</style>
</head>

<body class="bg-wsj-cream min-h-screen">

<!-- Nav -->
<nav class="bg-wsj-dark text-white py-3 px-6 sticky top-0 z-50 shadow-md no-print">
  <div class="max-w-[1600px] mx-auto flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="border-r border-gray-600 pr-3">
        <span class="font-serif text-xl font-bold tracking-tight">TERRENOS</span>
      </div>
      <span class="text-gray-400 text-sm font-sans">Córdoba · Reporte de Mercado</span>
    </div>
    <div class="flex items-center gap-4 text-xs font-sans">
      <a href="#water-safety" class="text-gray-400 hover:text-white transition">💧 Agua</a>
      <span class="text-gray-600">|</span>
      <span class="text-gray-400">zonaprop.com.ar</span>
    </div>
  </div>
</nav>

<!-- Main layout: content + sticky map -->
<div class="max-w-[1600px] mx-auto flex">
  <!-- Content column -->
  <main class="flex-1 min-w-0 px-4 sm:px-6 lg:px-8 py-8">
    <article class="bg-white shadow-sm rounded-lg border border-gray-200 px-6 sm:px-10 lg:px-14 py-10">
      {body}
      {arsenic_html}
    </article>
    <footer class="text-center text-gray-400 text-xs py-8 font-sans">
      Reporte generado automáticamente · Datos de ZonaProp
    </footer>
  </main>

  <!-- Sticky map sidebar -->
  <aside id="map-sidebar" class="hidden lg:block w-[420px] flex-shrink-0 no-print">
    <div id="map" class="rounded-l-lg shadow-lg"></div>
  </aside>
</div>

<script>
document.addEventListener("DOMContentLoaded", function() {{
  // ── Chart.js ──
  Chart.defaults.font.family = "'Helvetica Neue', Arial, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = "#555";
  Chart.defaults.plugins.legend.display = false;
  {chart_scripts}

  // ── Leaflet Map ──
  var mapEl = document.getElementById('map');
  if (!mapEl) return;

  var map = L.map('map', {{zoomControl: true}}).setView([-31.42, -64.35], 9);
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    maxZoom: 18,
  }}).addTo(map);

  var geojson = {geojson_js};
  var markers = {{}};

  function riskColor(risk) {{
    if (risk === 'low') return '#22c55e';
    if (risk === 'medium' || risk === 'low_to_medium') return '#f59e0b';
    if (risk === 'medium_to_high' || risk === 'high') return '#ef4444';
    return '#6b7280';
  }}

  L.geoJSON(geojson, {{
    pointToLayer: function(feature, latlng) {{
      var p = feature.properties;
      var marker = L.circleMarker(latlng, {{
        radius: 7,
        fillColor: riskColor(p.arsenic_risk),
        color: '#fff',
        weight: 2,
        opacity: 1,
        fillOpacity: 0.8,
      }});
      var popup = '<div style="min-width:200px">';
      if (p.image) popup += '<img src="' + p.image + '" style="width:100%;max-height:120px;object-fit:cover;border-radius:4px;margin-bottom:8px" />';
      popup += '<strong>' + p.location + '</strong><br>';
      popup += '<b>' + (p.price_text || '') + '</b>';
      if (p.size_m2) popup += ' · ' + p.size_m2.toLocaleString() + ' m²';
      if (p.price_per_m2) popup += '<br>USD ' + p.price_per_m2.toFixed(2) + '/m²';
      popup += '<br><span style="font-size:11px">Arsénico: <b>' + p.arsenic_risk.toUpperCase() + '</b> (' + p.arsenic_range + ' μg/L)</span>';
      if (p.link) popup += '<br><a href="' + p.link + '" target="_blank" style="color:#0274B6">Ver publicación →</a>';
      popup += '</div>';
      marker.bindPopup(popup);
      markers[p.id] = marker;
      return marker;
    }}
  }}).addTo(map);

  {lake_markers_js}

  // Legend
  var legend = L.control({{position: 'bottomright'}});
  legend.onAdd = function() {{
    var div = L.DomUtil.create('div', 'leaflet-control');
    div.style.cssText = 'background:white;padding:8px 12px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.2);font-size:11px;line-height:1.6';
    div.innerHTML = '<b>Riesgo Arsénico</b><br>' +
      '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#22c55e;margin-right:4px"></span> Bajo<br>' +
      '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#f59e0b;margin-right:4px"></span> Medio<br>' +
      '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#ef4444;margin-right:4px"></span> Alto<br>' +
      '<hr style="margin:4px 0;border-color:#eee">' +
      '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#fecaca;border:2px solid #dc2626;margin-right:4px"></span> Lago contaminado<br>' +
      '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#fef3c7;border:2px solid #f59e0b;margin-right:4px"></span> Lago en riesgo';
    return div;
  }};
  legend.addTo(map);

  // ── Scroll tracking: highlight listing on map ──
  var activeMarker = null;
  var cards = document.querySelectorAll('.listing-card[data-listing-num]');

  // Build listing-to-marker mapping from data
  var listingIndex = {json.dumps({str(i+1): l.get("id","") for i, l in enumerate(sorted(listings_data, key=lambda x: x.get("price_per_m2") or 99999))}, ensure_ascii=False)};

  var pulseCircle = null;

  var observer = new IntersectionObserver(function(entries) {{
    entries.forEach(function(entry) {{
      if (entry.isIntersecting) {{
        var num = entry.target.getAttribute('data-listing-num');
        var id = listingIndex[num];
        if (id && markers[id]) {{
          // Reset previous marker
          if (activeMarker) {{
            activeMarker.setStyle({{ weight: 2, radius: 7, fillOpacity: 0.8 }});
            if (activeMarker._path) activeMarker._path.classList.remove('leaflet-marker-active');
          }}
          // Remove previous pulse circle
          if (pulseCircle) {{ map.removeLayer(pulseCircle); }}

          // Highlight new marker
          var m = markers[id];
          m.setStyle({{ weight: 5, radius: 14, fillOpacity: 1, color: '#ff0000' }});
          m.bringToFront();
          if (m._path) m._path.classList.add('leaflet-marker-active');

          // Add pulsing outer ring
          pulseCircle = L.circleMarker(m.getLatLng(), {{
            radius: 24, weight: 3, color: '#0274B6', fillColor: '#0274B6',
            fillOpacity: 0.15, dashArray: '6 4', className: 'leaflet-marker-active'
          }}).addTo(map);

          m.openPopup();
          map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 11), {{ animate: true, duration: 0.8 }});
          activeMarker = m;

          // Highlight card with dashed border
          cards.forEach(function(c) {{ c.classList.remove('active-listing'); }});
          entry.target.classList.add('active-listing');
        }}
      }}
    }});
  }}, {{ threshold: 0.3, rootMargin: '-10% 0px -50% 0px' }});

  cards.forEach(function(card) {{ observer.observe(card); }});
}});
</script>

</body>
</html>'''


# ── Main ──

def main():
    if not os.path.exists(INPUT_MD):
        print(f"Error: {INPUT_MD} not found.")
        sys.exit(1)

    with open(INPUT_MD, "r", encoding="utf-8") as f:
        md = f.read()

    r = Renderer()
    body = r.render(md)
    arsenic_html = arsenic_section_html()
    html = html_page(body, r.charts, arsenic_html)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Rendered: {INPUT_MD} → {OUTPUT}")
    print(f"  Charts: {len(r.charts)}")
    print(f"  Map markers: {len([l for l in listings_data if l.get('lat')])}")
    print(f"  Arsenic data: {'yes' if arsenic_data else 'no'}")
    print(f"  Size: {len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
