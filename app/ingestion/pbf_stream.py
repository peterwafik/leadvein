"""Streaming PBF -> NormalizedLead. Memory-bounded: pyosmium dispatches elements
one at a time, but output is buffered (yield happens after parsing completes).
Way locations resolve via an osmium node-location index (file-backed for country
extracts, in-memory for fixtures). Whole-planet is out of scope.

pyosmium 4.0.2 API adaptations (verified against installed package):
1. osmium.InvalidLocationError — exists as osmium._osmium.InvalidLocationError,
   importable directly as osmium.InvalidLocationError. No rename needed.
2. location.valid() — IS a bound method (not a property); call as valid().
3. apply_file(path, locations=True, idx='flex_mem') — 'flex_mem' is the valid
   in-memory index name in 4.0.2; confirmed via SimpleHandler.apply_file help.
4. For node_cache_path (file-backed real-extract index): use
   'sparse_file_array,<path>' string passed to idx=. Windows path quirks may
   apply for very long paths; not exercised by fixture tests.
5. FileProcessor and SimpleWriter both exist in 4.0.2; used in builder script.
"""
from __future__ import annotations

from typing import Iterator

import osmium

from app.adapters.base import NormalizedLead
from app.adapters.osm_common import normalized_from_tags
from app.adapters.osm_tags import match_categories

_PROGRESS_EVERY = 10_000


class _Collector(osmium.SimpleHandler):
    def __init__(self, source_key: str, progress_cb=None):
        super().__init__()
        self.source_key = source_key
        self.progress_cb = progress_cb
        self.elements_seen = 0
        self.out: list[NormalizedLead] = []

    def _tick(self):
        self.elements_seen += 1
        if self.progress_cb and self.elements_seen % _PROGRESS_EVERY == 0:
            self.progress_cb(self.elements_seen)

    def _handle(self, tags: dict, lat, lon, raw_ref: str):
        cats = match_categories(tags)
        if not cats:
            return
        n = normalized_from_tags(tags, lat=lat, lon=lon, raw_ref=raw_ref,
                                 categories=cats, source_key=self.source_key)
        if n is not None:
            self.out.append(n)

    def node(self, n):
        self._tick()
        tags = dict(n.tags)
        if not tags:
            # bare location node — no business data, skip tag processing
            return
        self._handle(tags, n.location.lat, n.location.lon, f"node/{n.id}")

    def way(self, w):
        self._tick()
        tags = dict(w.tags)
        if not tags:
            return
        lats, lons = [], []
        for i, nd in enumerate(w.nodes):
            # Skip last node if it closes the ring (same ref as first node)
            if i == len(w.nodes) - 1 and len(w.nodes) > 1 and w.nodes[-1].ref == w.nodes[0].ref:
                continue
            try:
                if nd.location.valid():
                    lats.append(nd.location.lat)
                    lons.append(nd.location.lon)
            except osmium.InvalidLocationError:
                continue
        lat = sum(lats) / len(lats) if lats else None
        lon = sum(lons) / len(lons) if lons else None
        self._handle(tags, lat, lon, f"way/{w.id}")


def stream_business_leads(pbf_path: str, *, source_key: str,
                          node_cache_path: str | None = None,
                          progress_cb=None) -> Iterator[NormalizedLead]:
    """Stream NormalizedLeads from a PBF file.

    Args:
        pbf_path: Path to the .osm.pbf file to stream.
        source_key: Source attribution key (e.g. 'osm_geofabrik').
        node_cache_path: Optional path for file-backed node location index
            (for large country extracts). If None, uses in-memory 'flex_mem'.
        progress_cb: Optional callable(elements_seen: int); called every
            10_000 elements AND once more after the file is fully processed
            with the final total, ensuring a flush call for small fixtures.

    Note: all matching leads are buffered internally during apply_file; the first
    item is not yielded until parsing completes. Do not rely on lazy/backpressure
    semantics.
    """
    handler = _Collector(source_key, progress_cb)
    if node_cache_path:
        idx = f"sparse_file_array,{node_cache_path}"
    else:
        idx = "flex_mem"
    handler.apply_file(pbf_path, locations=True, idx=idx)
    if progress_cb:
        # Final flush: ensures progress_cb fires at least once even when
        # elements_seen < _PROGRESS_EVERY (e.g. small fixture files).
        progress_cb(handler.elements_seen)
    yield from handler.out
