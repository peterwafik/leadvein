from __future__ import annotations

# categories that typically have high energy usage (heating, refrigeration, machines)
HIGH_ENERGY_CATEGORIES = {
    "restaurant", "takeaway", "cafe", "bakery", "hotel", "gym", "fitness_studio",
    "car_wash", "laundromat", "dry_cleaner", "convenience_store", "supermarket",
    "butcher", "warehouse", "manufacturer", "spa",
}


class UtilityEnergyProfile:
    key = "utility_energy"

    def _energy_likelihood(self, lead: dict) -> int:
        cats = set(lead.get("category_keys") or [])
        attrs = lead.get("attributes") or {}
        score = 30
        if cats & HIGH_ENERGY_CATEGORIES:
            score = 80
        if attrs.get("open_7_days"):
            score += 10
        if attrs.get("number_of_locations", 1) and attrs.get("number_of_locations", 1) > 1:
            score += 10
        return min(100, score)

    def combine(self, lead: dict, base: dict) -> dict:
        energy = self._energy_likelihood(lead)
        fit = energy  # for this vertical, fit == energy-usage likelihood
        subs = dict(base)
        subs["energy_usage_likelihood"] = energy
        subs["fit"] = fit
        # weighted blend
        total = round(
            0.35 * energy + 0.20 * base["contactability"] + 0.15 * base["freshness"]
            + 0.15 * base["confidence"] + 0.15 * base["compliance"])
        cats = ", ".join(lead.get("category_keys") or []) or "uncategorised"
        bits = [f"category: {cats}"]
        if (lead.get("attributes") or {}).get("open_7_days"):
            bits.append("open 7 days")
        if lead.get("phone"):
            bits.append("public phone")
        bits.append(f"energy-usage likelihood {energy}")
        explanation = f"Scored {total} — " + ", ".join(bits) + "."
        return {"subscores": subs, "total": total, "explanation": explanation}
