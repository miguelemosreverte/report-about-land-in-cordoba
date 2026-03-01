#!/usr/bin/env python3
"""
ZonaProp Crawler — Land listings in Córdoba, Argentina.
Two-pass scraper:
  Pass 1: List pages → basic data + thumbnails
  Pass 2: Individual listing pages → full description, extra photos, geocoding
Generates enriched markdown report with Chart.js + Leaflet directives.
"""

import json, os, re, time, random, hashlib, statistics
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
import requests

BASE_URL = "https://www.zonaprop.com.ar"
SEARCH_URL = f"{BASE_URL}/terrenos-venta-cordoba.html"
MAX_PAGES = 5
IMG_DIR = "images"
DATA_FILE = "data.json"
REPORT_FILE = "report.md"

os.makedirs(IMG_DIR, exist_ok=True)

# ── Known geocoordinates for Córdoba locations ──
# Fallback table; Nominatim is used first.
KNOWN_COORDS = {
    "Río Ceballos": (-31.164, -64.325),
    "Unquillo": (-31.232, -64.317),
    "Mendiolaza": (-31.269, -64.300),
    "Villa Allende": (-31.295, -64.295),
    "La Calera": (-31.345, -64.335),
    "Villa Carlos Paz": (-31.424, -64.497),
    "La Falda": (-31.093, -64.489),
    "La Cumbre": (-30.982, -64.494),
    "Cosquín": (-31.245, -64.469),
    "Alta Gracia": (-31.662, -64.432),
    "Villa Giardino": (-31.047, -64.498),
    "Santa Rosa de Calamuchita": (-32.068, -64.537),
    "Los Molinos": (-31.822, -64.607),
    "Potrero de Garay": (-31.777, -64.538),
    "Ascochinga": (-30.963, -64.265),
    "San Antonio de Arredondo": (-31.482, -64.521),
    "Estancia Vieja": (-31.398, -64.497),
    "Malagueño": (-31.462, -64.361),
    "Córdoba": (-31.420, -64.189),
    "Monte Cristo": (-31.340, -63.944),
    "Colonia Caroya": (-31.000, -64.088),
    "Villa del Lago": (-31.418, -64.530),
    "Santa María de Punilla": (-31.384, -64.464),
    "Los Cocos": (-30.937, -64.506),
    "San Roque": (-31.350, -64.450),
    "Manantiales": (-31.490, -64.150),
    "Nueva Córdoba": (-31.430, -64.185),
    "General Paz": (-31.412, -64.185),
    "Argüello": (-31.358, -64.240),
    "Villa Warcalde": (-31.365, -64.280),
    "Villa Rivera Indarte": (-31.360, -64.268),
    "Inaudi": (-31.467, -64.150),
    "DOCTA": (-31.462, -64.361),
    "Villa Esquiú": (-31.468, -64.140),
    "Observatorio": (-31.423, -64.192),
    "Centro": (-31.417, -64.183),
    "Colón": (-31.003, -64.100),
    "Río Segundo": (-31.654, -63.913),
}

# ── Helpers ──

def parse_price(text):
    if not text:
        return None, None
    text = text.strip().replace("\n", " ")
    currency = "USD" if any(k in text for k in ("USD", "U$S", "U\$S")) else "ARS"
    cleaned = text.replace(".", "").replace(",", "")
    nums = re.findall(r"\d+", cleaned)
    if nums:
        try:
            return int(nums[0]), currency
        except ValueError:
            pass
    return None, currency


def parse_size(text):
    if not text:
        return None
    cleaned = text.replace(".", "").replace(",", ".")
    nums = re.findall(r"[\d.]+", cleaned)
    if nums:
        try:
            return float(nums[0])
        except ValueError:
            pass
    return None


def download_image(url, name):
    if not url or url.startswith("data:"):
        return None
    try:
        ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".avif"):
            ext = ".jpg"
        fname = f"{name}{ext}"
        fpath = os.path.join(IMG_DIR, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
            return f"{IMG_DIR}/{fname}"
        r = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": BASE_URL,
        })
        if r.status_code == 200 and len(r.content) > 500:
            with open(fpath, "wb") as f:
                f.write(r.content)
            return f"{IMG_DIR}/{fname}"
    except Exception as e:
        print(f"    img-dl err: {e}")
    return None


def geocode_nominatim(query):
    """Geocode via Nominatim (respect 1 req/s)."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1,
                    "countrycodes": "ar"},
            headers={"User-Agent": "cordoba-land-report/1.0"},
            timeout=10,
        )
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None


def geocode_location(location_str):
    """Try known coords, then Nominatim."""
    parts = [p.strip() for p in location_str.split(",")]
    name = parts[0]

    # Try known coords
    if name in KNOWN_COORDS:
        return KNOWN_COORDS[name]

    # Try Nominatim with full string + Córdoba
    query = f"{location_str}, Córdoba, Argentina"
    coords = geocode_nominatim(query)
    if coords:
        time.sleep(1.1)  # respect rate limit
        return coords

    # Try just the neighborhood name
    coords = geocode_nominatim(f"{name}, Córdoba, Argentina")
    if coords:
        time.sleep(1.1)
        return coords

    return None


# ── Pass 1: List page scraping ──

def scrape_page(page, url):
    print(f"  → {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(2, 4))

    for sel in ['button:has-text("Aceptar")', 'button:has-text("Entendido")',
                'button:has-text("Cerrar")', '[class*="cookie"] button']:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(0.3)
        except Exception:
            pass

    page.wait_for_selector(
        '[data-qa="posting PROPERTY"], .postingCardLayout, article[data-id]',
        timeout=15000,
    )

    cards = (page.query_selector_all('[data-qa="posting PROPERTY"]')
             or page.query_selector_all('.postingCardLayout')
             or page.query_selector_all('[class*="postingCard"]')
             or page.query_selector_all('article[data-id]')
             or page.query_selector_all('[data-posting-type]'))
    print(f"  cards: {len(cards)}")
    listings = []

    for card in cards:
        try:
            l = {}
            el = (card.query_selector('[data-qa="POSTING_CARD_DESCRIPTION"]')
                  or card.query_selector('h2')
                  or card.query_selector('[class*="title"]'))
            l["title"] = el.inner_text().strip() if el else ""

            el = (card.query_selector('[data-qa="POSTING_CARD_LOCATION"]')
                  or card.query_selector('[class*="location"]'))
            l["location"] = el.inner_text().strip() if el else ""

            el = (card.query_selector('[data-qa="POSTING_CARD_PRICE"]')
                  or card.query_selector('[class*="price"]'))
            price_text = el.inner_text().strip() if el else ""
            l["price_text"] = price_text
            l["price_value"], l["currency"] = parse_price(price_text)

            feats = card.query_selector_all(
                '[data-qa="POSTING_CARD_FEATURES"] span, '
                '[class*="postingCardFeatures"] span, '
                '[class*="feature"] span')
            size_text = ""
            for fe in feats:
                t = fe.inner_text()
                if "m²" in t or "m2" in t:
                    size_text = t
                    if "tot" in t.lower():
                        break
            if not size_text:
                el = card.query_selector('[class*="surface"]')
                if el:
                    size_text = el.inner_text().strip()
            l["size_text"] = size_text
            l["size_m2"] = parse_size(size_text)

            a = (card.query_selector('a[href*="/terreno"], a[href*="/lote"], '
                                     'a[href*="/propiedad"]')
                 or card.query_selector('a[href]'))
            href = a.get_attribute("href") if a else ""
            if href and not href.startswith("http"):
                href = BASE_URL + href
            l["link"] = href

            img_url = None
            img_el = card.query_selector(
                'img[src*="img"], img[data-src], img[src*="zonaprop"], '
                'img[src*="clasificado"], img[src*="http"]')
            if img_el:
                img_url = img_el.get_attribute("data-src") or img_el.get_attribute("src")
            if not img_url:
                src_el = card.query_selector("picture source[srcset]")
                if src_el:
                    srcset = src_el.get_attribute("srcset") or ""
                    parts = srcset.split(",")
                    if parts:
                        img_url = parts[-1].strip().split(" ")[0]
            if not img_url:
                any_img = card.query_selector("img[src]")
                if any_img:
                    img_url = any_img.get_attribute("src")
            l["image_url"] = img_url or ""

            if l["price_value"] and l["size_m2"] and l["size_m2"] > 0:
                l["price_per_m2"] = round(l["price_value"] / l["size_m2"], 2)
            else:
                l["price_per_m2"] = None

            m = re.search(r"-(\d{6,})\.html", href)
            l["id"] = m.group(1) if m else hashlib.md5(href.encode()).hexdigest()[:10]

            # Will be filled in pass 2
            l["description"] = ""
            l["extra_images"] = []
            l["features"] = []
            l["lat"] = None
            l["lng"] = None

            listings.append(l)
        except Exception as e:
            print(f"    card-err: {e}")

    return listings


# ── Pass 2: Individual listing detail scraping ──

def scrape_detail(page, listing):
    """Visit individual listing page for richer data."""
    url = listing.get("link")
    if not url:
        return listing

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.uniform(1.5, 3))

        # Full description
        desc_el = (page.query_selector('[class*="section-description"] p')
                   or page.query_selector('[data-qa="POSTING_DESCRIPTION"]')
                   or page.query_selector('[class*="description"]'))
        if desc_el:
            listing["description"] = desc_el.inner_text().strip()[:500]

        # Features list
        feat_els = page.query_selector_all(
            '[class*="feature-item"], [class*="icon-feature"] + span, '
            '[data-qa*="FEATURE"] span')
        listing["features"] = list(set(
            f.inner_text().strip() for f in feat_els if f.inner_text().strip()
        ))[:15]

        # Extra images (up to 5)
        img_els = page.query_selector_all(
            '[class*="gallery"] img, [class*="carousel"] img, '
            '[class*="slider"] img, [class*="photo"] img')
        seen = {listing.get("image_url", "")}
        extra = []
        for img in img_els:
            src = img.get_attribute("data-src") or img.get_attribute("src") or ""
            if src and src not in seen and not src.startswith("data:") and "logo" not in src:
                seen.add(src)
                extra.append(src)
            if len(extra) >= 5:
                break
        listing["extra_images"] = extra

    except Exception as e:
        print(f"    detail-err ({listing['id']}): {e}")

    return listing


# ── Geocoding pass ──

def geocode_all(listings):
    """Geocode all listings, caching by location string."""
    cache = {}
    for i, l in enumerate(listings):
        loc = l["location"]
        if loc in cache:
            l["lat"], l["lng"] = cache[loc]
        else:
            coords = geocode_location(loc)
            if coords:
                l["lat"], l["lng"] = coords
                cache[loc] = coords
                print(f"  [{i+1}] ✓ {loc} → ({coords[0]:.4f}, {coords[1]:.4f})")
            else:
                cache[loc] = (None, None)
                print(f"  [{i+1}] ✗ {loc} → no coords")
    return listings


# ── Rankings ──

def compute_rankings(data):
    usd = [l for l in data if l.get("price_value") and l["currency"] == "USD"]
    both = [l for l in data if l.get("price_per_m2") and l["currency"] == "USD"]
    sized = [l for l in data if l.get("size_m2")]
    return {
        "cheapest_total": sorted(usd, key=lambda x: x["price_value"])[:15],
        "most_expensive": sorted(usd, key=lambda x: -x["price_value"])[:10],
        "cheapest_per_m2": sorted(both, key=lambda x: x["price_per_m2"])[:15],
        "most_expensive_per_m2": sorted(both, key=lambda x: -x["price_per_m2"])[:10],
        "largest": sorted(sized, key=lambda x: -x["size_m2"])[:10],
        "best_value": _best_value(both)[:15],
    }


def _best_value(listings):
    if not listings:
        return []
    max_ppm = max(l["price_per_m2"] for l in listings) or 1
    max_size = max(l.get("size_m2", 1) for l in listings) or 1
    scored = []
    for l in listings:
        ppm_score = 1 - (l["price_per_m2"] / max_ppm)
        size_score = min((l.get("size_m2", 0) / 2000), 1.0)
        score = ppm_score * 0.65 + size_score * 0.35
        scored.append({**l, "_score": round(score, 3)})
    return sorted(scored, key=lambda x: -x["_score"])


def zone_stats(data):
    zones = {}
    for l in data:
        if not l.get("price_per_m2") or l["currency"] != "USD":
            continue
        z = l["location"].split(",")[0].strip() or "Sin ubicación"
        zones.setdefault(z, []).append(l)
    result = []
    for z, items in zones.items():
        ppms = [i["price_per_m2"] for i in items]
        prices = [i["price_value"] for i in items]
        sizes = [i["size_m2"] for i in items if i.get("size_m2")]
        result.append({
            "zone": z, "count": len(items),
            "avg_ppm": round(statistics.mean(ppms), 2),
            "min_ppm": round(min(ppms), 2),
            "max_ppm": round(max(ppms), 2),
            "avg_price": round(statistics.mean(prices)),
            "avg_size": round(statistics.mean(sizes)) if sizes else 0,
        })
    return sorted(result, key=lambda x: x["avg_ppm"])


# ── Report generation ──

def listing_card_md(l, rank=None):
    rank_str = f"**#{rank}** — " if rank else ""
    img = f"![{l['location']}]({l['image_local']})" if l.get("image_local") else ""
    price = l.get("price_text", "N/A")
    size = f"{l['size_m2']:,.0f} m²" if l.get("size_m2") else l.get("size_text", "N/A")
    ppm = f"USD {l['price_per_m2']:,.2f}/m²" if l.get("price_per_m2") else ""
    link = f"[Ver publicación]({l['link']})" if l.get("link") else ""
    desc = l.get("description", "")[:200]
    lines = [img, "",
             f"{rank_str}**{l.get('location', 'N/A')}**", "",
             f"- **Precio:** {price}",
             f"- **Superficie:** {size}"]
    if ppm:
        lines.append(f"- **Precio/m²:** {ppm}")
    if l.get("title"):
        lines.append(f"- {l['title'][:120]}")
    if desc:
        lines.append(f"- {desc}")
    lines.append(f"- {link}")
    lines.append("")
    return "\n".join(lines)


def generate_report(data, rankings, zones):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    usd = [l for l in data if l.get("price_value") and l["currency"] == "USD"]
    sized = [l for l in data if l.get("size_m2")]
    both = [l for l in data if l.get("price_per_m2") and l["currency"] == "USD"]

    L = []
    w = L.append

    w("# Terrenos en Venta en Córdoba")
    w("")
    w(f"**Reporte de mercado** · {now} · Fuente: [zonaprop.com.ar]({SEARCH_URL})")
    w("")
    w("---")
    w("")

    # Summary
    w("## Resumen del Mercado")
    w("")
    if usd:
        prices = [l["price_value"] for l in usd]
        w(f"- **Publicaciones analizadas:** {len(data)}")
        w(f"- **Rango de precios (USD):** ${min(prices):,} – ${max(prices):,}")
        w(f"- **Precio promedio:** ${statistics.mean(prices):,.0f}")
        w(f"- **Precio mediano:** ${statistics.median(prices):,.0f}")
    if sized:
        sizes = [l["size_m2"] for l in sized]
        w(f"- **Superficie:** {min(sizes):,.0f} m² – {max(sizes):,.0f} m²")
        w(f"- **Superficie promedio:** {statistics.mean(sizes):,.0f} m²")
    if both:
        ppms = [l["price_per_m2"] for l in both]
        w(f"- **Precio/m² promedio (USD):** ${statistics.mean(ppms):,.2f}")
        w(f"- **Precio/m² mediano (USD):** ${statistics.median(ppms):,.2f}")
    w("")

    # Charts
    w("## Distribución de Precios")
    w("")
    if usd:
        buckets = {}
        for l in usd:
            p = l["price_value"]
            if p < 25000: b = "< 25K"
            elif p < 50000: b = "25K–50K"
            elif p < 75000: b = "50K–75K"
            elif p < 100000: b = "75K–100K"
            elif p < 150000: b = "100K–150K"
            elif p < 250000: b = "150K–250K"
            elif p < 500000: b = "250K–500K"
            else: b = "500K+"
            buckets[b] = buckets.get(b, 0) + 1
        order = ["< 25K", "25K–50K", "50K–75K", "75K–100K",
                 "100K–150K", "150K–250K", "250K–500K", "500K+"]
        labels = [b for b in order if b in buckets]
        values = [buckets[b] for b in labels]
        chart1 = {
            "type": "bar",
            "data": {"labels": labels, "datasets": [{
                "label": "Cantidad de terrenos", "data": values,
                "backgroundColor": "rgba(2, 116, 182, 0.75)",
                "borderColor": "rgba(2, 116, 182, 1)", "borderWidth": 1}]},
            "options": {"plugins": {"title": {"display": True,
                "text": "Distribución de Precios (USD)"}},
                "scales": {"y": {"beginAtZero": True,
                    "title": {"display": True, "text": "Cantidad"}},
                    "x": {"title": {"display": True, "text": "Rango de precio"}}}}
        }
        w("```chart")
        w(json.dumps(chart1, ensure_ascii=False))
        w("```")
        w("")

    if zones:
        top_zones = zones[:20]
        chart2 = {
            "type": "bar",
            "data": {"labels": [z["zone"][:25] for z in top_zones],
                     "datasets": [{"label": "Precio/m² promedio (USD)",
                        "data": [z["avg_ppm"] for z in top_zones],
                        "backgroundColor": "rgba(34, 139, 34, 0.65)",
                        "borderColor": "rgba(34, 139, 34, 1)", "borderWidth": 1}]},
            "options": {"indexAxis": "y",
                "plugins": {"title": {"display": True,
                    "text": "Precio/m² por Zona (más económicas primero)"}},
                "scales": {"x": {"beginAtZero": True,
                    "title": {"display": True, "text": "USD/m²"}}}}
        }
        w("```chart")
        w(json.dumps(chart2, ensure_ascii=False))
        w("```")
        w("")

    if both:
        scatter_data = [{"x": l["size_m2"], "y": l["price_value"]}
                        for l in both if l["size_m2"] < 15000 and l["price_value"] < 500000]
        chart3 = {
            "type": "scatter",
            "data": {"datasets": [{"label": "Superficie vs Precio",
                "data": scatter_data,
                "backgroundColor": "rgba(2, 116, 182, 0.5)", "pointRadius": 5}]},
            "options": {"plugins": {"title": {"display": True,
                "text": "Relación Superficie vs Precio (< 500K USD, < 15.000 m²)"}},
                "scales": {"x": {"title": {"display": True, "text": "Superficie (m²)"}},
                    "y": {"title": {"display": True, "text": "Precio (USD)"},
                           "beginAtZero": True}}}
        }
        w("```chart")
        w(json.dumps(chart3, ensure_ascii=False))
        w("```")
        w("")

    # Rankings
    w("---")
    w("")
    w("## Rankings")
    w("")
    w("### Mejor Relación Calidad-Precio")
    w("")
    w("> Score compuesto: 65% precio/m² + 35% tamaño óptimo (~2.000 m²)")
    w("")
    for i, l in enumerate(rankings["best_value"][:10], 1):
        w(listing_card_md(l, rank=i))

    w("---")
    w("")
    w("### Más Económicos por m²")
    w("")
    for i, l in enumerate(rankings["cheapest_per_m2"][:10], 1):
        w(listing_card_md(l, rank=i))

    w("---")
    w("")
    w("### Más Económicos (precio total)")
    w("")
    for i, l in enumerate(rankings["cheapest_total"][:10], 1):
        w(listing_card_md(l, rank=i))

    w("---")
    w("")
    w("### Terrenos Más Grandes")
    w("")
    for i, l in enumerate(rankings["largest"][:10], 1):
        w(listing_card_md(l, rank=i))

    w("---")
    w("")

    # Zone analysis
    w("## Análisis por Zona")
    w("")
    w("| Zona | Cant. | Precio/m² Prom. | Precio/m² Mín. | Precio/m² Máx. | Precio Prom. | Sup. Prom. |")
    w("|------|------:|----------------:|---------------:|---------------:|-------------:|-----------:|")
    for z in zones:
        w(f"| {z['zone'][:35]} | {z['count']} | ${z['avg_ppm']:,.2f} "
          f"| ${z['min_ppm']:,.2f} | ${z['max_ppm']:,.2f} "
          f"| ${z['avg_price']:,} | {z['avg_size']:,} m² |")
    w("")

    # Full listing table
    w("---")
    w("")
    w("## Listado Completo")
    w("")
    w("| # | Imagen | Ubicación | Superficie | Precio | Precio/m² | Link |")
    w("|--:|--------|-----------|----------:|-------:|----------:|------|")
    for i, l in enumerate(
            sorted(data, key=lambda x: x.get("price_per_m2") or 99999), 1):
        loc = l.get("location", "").replace("|", "–")[:45]
        sz = f"{l['size_m2']:,.0f} m²" if l.get("size_m2") else "—"
        pr = l.get("price_text", "—").replace("|", "–")
        ppm = f"${l['price_per_m2']:,.2f}" if l.get("price_per_m2") else "—"
        img = f"![thumb]({l['image_local']})" if l.get("image_local") else "—"
        link = f"[Ver]({l['link']})" if l.get("link") else "—"
        w(f"| {i} | {img} | {loc} | {sz} | {pr} | {ppm} | {link} |")
    w("")

    w("---")
    w("")
    w("*Reporte generado automáticamente. Precios y disponibilidad sujetos a cambios. "
      "Consultar en [ZonaProp](https://www.zonaprop.com.ar) para información actualizada.*")
    w("")

    return "\n".join(L)


# ── Main ──

def main():
    print("=" * 60)
    print(" ZonaProp Crawler — Terrenos en Córdoba (Enhanced)")
    print("=" * 60)

    all_listings = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        page = ctx.new_page()

        # ── PASS 1: List pages ──
        print("\n── PASS 1: Scraping list pages ──")
        for pn in range(1, MAX_PAGES + 1):
            url = SEARCH_URL if pn == 1 else \
                f"{BASE_URL}/terrenos-venta-cordoba-pagina-{pn}.html"
            print(f"\n[Página {pn}/{MAX_PAGES}]")
            try:
                batch = scrape_page(page, url)
                all_listings.extend(batch)
                print(f"  total: {len(all_listings)}")
                if not batch:
                    break
                time.sleep(random.uniform(1.5, 3))
            except Exception as e:
                print(f"  ERROR: {e}")
                page.screenshot(path=f"debug_p{pn}.png")
                break

        # ── PASS 2: Detail pages (sample up to 50 for speed) ──
        print(f"\n── PASS 2: Scraping detail pages (up to 50) ──")
        detail_count = min(50, len(all_listings))
        for i in range(detail_count):
            l = all_listings[i]
            print(f"  [{i+1}/{detail_count}] {l['id']} — {l['location'][:40]}")
            scrape_detail(page, l)
            time.sleep(random.uniform(0.5, 1.5))

        browser.close()

    # ── PASS 3: Geocoding ──
    print(f"\n── PASS 3: Geocoding {len(all_listings)} listings ──")
    geocode_all(all_listings)

    # ── PASS 4: Download images ──
    print(f"\n── PASS 4: Downloading images ──")
    for i, l in enumerate(all_listings):
        # Main thumbnail
        local = download_image(l.get("image_url"), l["id"])
        l["image_local"] = local

        # Extra images from detail page
        extra_locals = []
        for j, eurl in enumerate(l.get("extra_images", [])):
            elocal = download_image(eurl, f"{l['id']}_extra{j}")
            if elocal:
                extra_locals.append(elocal)
        l["extra_images_local"] = extra_locals

        status = "✓" if local else "–"
        extras = f" +{len(extra_locals)}" if extra_locals else ""
        print(f"  [{i+1}/{len(all_listings)}] {status}{extras} {l['id']}")
        time.sleep(random.uniform(0.05, 0.2))

    # Save JSON
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_listings, f, ensure_ascii=False, indent=2)
    print(f"\nData saved: {DATA_FILE}")

    # Generate report
    rankings = compute_rankings(all_listings)
    zones = zone_stats(all_listings)
    md = generate_report(all_listings, rankings, zones)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Report saved: {REPORT_FILE}")


if __name__ == "__main__":
    main()
