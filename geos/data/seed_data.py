"""Static world model: India's crude supply ecosystem.

Numbers are realistic, public-domain approximations used for simulation. They
are intentionally explicit so scenario outputs can be audited. Coordinates are
[lat, lon] for geospatial rendering in the command center.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Supplier:
    id: str
    name: str
    country: str
    coords: List[float]
    share: float                 # fraction of India's crude imports
    grade: str                   # crude grade family
    via_hormuz: bool             # transits the Strait of Hormuz
    spot_premium_usd: float      # premium over Brent for spot lifting
    reliability: float           # 0-1 historical reliability
    lead_time_days: int          # voyage time to Indian west-coast ports


@dataclass
class Corridor:
    id: str
    name: str
    waypoints: List[List[float]]
    base_risk: float             # 0-1 baseline disruption probability
    daily_throughput_mbpd: float


@dataclass
class Refinery:
    id: str
    name: str
    coords: List[float]
    capacity_mbpd: float
    complexity: float            # Nelson-style complexity proxy 0-1
    compatible_grades: List[str]


@dataclass
class Reserve:
    id: str
    name: str
    coords: List[float]
    capacity_mmbbl: float        # million barrels
    fill_pct: float


# --- Crude suppliers (FY2024-25 approximate import mix) ---
SUPPLIERS: List[Supplier] = [
    Supplier("sup_ru", "Russia (Urals/ESPO)", "Russia", [55.75, 37.62], 0.36,
             "medium_sour", False, 4.5, 0.82, 32),
    Supplier("sup_iq", "Iraq (Basrah)", "Iraq", [30.51, 47.78], 0.20,
             "medium_sour", True, 2.0, 0.85, 12),
    Supplier("sup_sa", "Saudi Arabia (Arab Light)", "Saudi Arabia", [26.43, 50.10], 0.15,
             "medium_sour", True, 1.5, 0.93, 11),
    Supplier("sup_ae", "UAE (Murban)", "UAE", [24.47, 54.37], 0.08,
             "light_sour", True, 1.2, 0.94, 9),
    Supplier("sup_us", "USA (WTI/Mars)", "USA", [29.76, -93.0], 0.07,
             "light_sweet", False, 3.8, 0.90, 40),
    Supplier("sup_ng", "Nigeria (Bonny Light)", "Nigeria", [4.45, 7.16], 0.05,
             "light_sweet", False, 2.6, 0.78, 24),
    Supplier("sup_br", "Brazil (Tupi)", "Brazil", [-22.9, -43.2], 0.04,
             "medium_sweet", False, 3.0, 0.83, 38),
    Supplier("sup_ku", "Kuwait (KEC)", "Kuwait", [29.37, 47.98], 0.05,
             "medium_sour", True, 1.8, 0.90, 11),
]

# --- Shipping corridors ---
CORRIDORS: List[Corridor] = [
    Corridor("cor_hormuz", "Strait of Hormuz",
             [[26.57, 56.25], [26.0, 56.5]], 0.18, 2.1),
    Corridor("cor_redsea", "Red Sea / Bab-el-Mandeb",
             [[12.58, 43.33], [20.0, 38.5]], 0.30, 0.4),
    Corridor("cor_malacca", "Strait of Malacca",
             [[1.43, 102.9], [3.0, 100.5]], 0.10, 0.9),
    Corridor("cor_capeofgood", "Cape of Good Hope (reroute)",
             [[-34.35, 18.47], [-15.0, 12.0]], 0.05, 0.3),
    Corridor("cor_atlantic", "Atlantic Approaches",
             [[20.0, -30.0], [10.0, -20.0]], 0.04, 0.5),
]

# --- Indian refineries (west + east coast majors) ---
REFINERIES: List[Refinery] = [
    Refinery("ref_jamnagar", "Jamnagar (Reliance)", [22.34, 69.86], 1.24, 0.95,
             ["medium_sour", "light_sour", "medium_sweet", "light_sweet"]),
    Refinery("ref_vadinar", "Vadinar (Nayara)", [22.36, 69.70], 0.40, 0.80,
             ["medium_sour", "light_sour"]),
    Refinery("ref_mumbai", "Mumbai (BPCL/HPCL)", [19.00, 72.85], 0.45, 0.70,
             ["medium_sour", "medium_sweet"]),
    Refinery("ref_paradip", "Paradip (IOCL)", [20.26, 86.67], 0.30, 0.85,
             ["medium_sour", "light_sweet", "medium_sweet"]),
    Refinery("ref_mangalore", "Mangalore (MRPL)", [12.92, 74.86], 0.30, 0.75,
             ["medium_sour", "light_sour"]),
]

# --- Strategic Petroleum Reserves ---
RESERVES: List[Reserve] = [
    Reserve("res_vizag", "Visakhapatnam", [17.69, 83.22], 9.77, 0.95),
    Reserve("res_mangalore", "Mangalore", [12.92, 74.86], 11.0, 0.90),
    Reserve("res_padur", "Padur", [13.45, 74.74], 18.3, 0.88),
]

PORTS = {
    "Jamnagar": [22.34, 69.86],
    "Mumbai": [19.00, 72.85],
    "Mangalore": [12.92, 74.86],
    "Paradip": [20.26, 86.67],
    "Visakhapatnam": [17.69, 83.22],
}

INDIA_CENTER = [21.5, 78.0]


def total_import_share_via(corridor_id: str) -> float:
    """Fraction of India's crude imports exposed to a given corridor."""
    if corridor_id == "cor_hormuz":
        return sum(s.share for s in SUPPLIERS if s.via_hormuz)
    return 0.0
