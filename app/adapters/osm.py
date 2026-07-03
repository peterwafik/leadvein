from __future__ import annotations

from typing import Iterable

import requests

from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead
from app.adapters.osm_common import normalized_from_tags
from app.adapters.osm_tags import match_categories

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = ("LeadVault/0.1 (+https://example.com/contact; "
              "youssef.zaki@student.giu-uni.de)")

# taxonomy key -> OSM tag (key=value). This map is the ONLY place OSM tagging lives.
CATEGORY_TO_OSM = {
    "restaurant": "amenity=restaurant", "takeaway": "amenity=fast_food",
    "cafe": "amenity=cafe", "bakery": "shop=bakery", "bar": "amenity=bar",
    "pub": "amenity=pub", "hotel": "tourism=hotel", "gym": "leisure=fitness_centre",
    "fitness_studio": "leisure=fitness_centre", "hair_salon": "shop=hairdresser",
    "barber_shop": "shop=hairdresser", "nail_salon": "shop=beauty", "spa": "leisure=spa",
    "dental_clinic": "amenity=dentist", "medical_clinic": "amenity=clinic",
    "car_wash": "amenity=car_wash", "auto_repair": "shop=car_repair",
    "convenience_store": "shop=convenience", "supermarket": "shop=supermarket",
    "laundromat": "shop=laundry", "dry_cleaner": "shop=dry_cleaning",
    "butcher": "shop=butcher", "florist": "shop=florist", "pharmacy": "amenity=pharmacy",
    "clothing_store": "shop=clothes", "hardware_store": "shop=hardware",
}


def build_overpass_ql(area: dict, categories: list[str], limit: int = 100) -> str:
    city = area.get("city") or area.get("region") or ""
    selectors = []
    for c in categories:
        tag = CATEGORY_TO_OSM.get(c)
        if not tag:
            continue
        k, v = tag.split("=", 1)
        selectors.append(f'node["{k}"="{v}"](area.searchArea);')
        selectors.append(f'way["{k}"="{v}"](area.searchArea);')
    body = "\n".join(selectors)
    return (f'[out:json][timeout:60];\n'
            f'area["name"="{city}"]->.searchArea;\n'
            f'(\n{body}\n);\n'
            f'out center {limit};')


class OsmOverpassAdapter:
    meta = SourceMeta(key="osm_overpass", name="OpenStreetMap (Overpass)",
                      type="open_data", url=OVERPASS_URL,
                      license="ODbL (OpenStreetMap contributors)")

    def discover(self, query: AdapterQuery, *, session=requests) -> Iterable[dict]:
        ql = build_overpass_ql(query.area, query.categories, query.limit)
        resp = session.post(OVERPASS_URL, data={"data": ql},
                            headers={"User-Agent": USER_AGENT}, timeout=90)
        resp.raise_for_status()
        return resp.json().get("elements", [])

    def normalize(self, raw: dict) -> NormalizedLead | None:
        tags = raw.get("tags") or {}
        cats = match_categories(tags)
        lat = raw.get("lat") or (raw.get("center") or {}).get("lat")
        lon = raw.get("lon") or (raw.get("center") or {}).get("lon")
        lead = normalized_from_tags(
            tags, lat=lat, lon=lon,
            raw_ref=f"{raw.get('type', 'node')}/{raw.get('id', '')}",
            categories=cats, source_key=self.meta.key,
        )
        if lead is not None:
            lead.source_url = OVERPASS_URL
            lead.source_license = self.meta.license
        return lead

    def attribution(self) -> str:
        return "© OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright)"
