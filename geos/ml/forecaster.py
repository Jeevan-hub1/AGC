"""Geopolitical Risk Foundation Model (predictive layer).

A genuinely *trained* ML model that forecasts the probability a shipping
corridor is disrupted in the next horizon, and estimates the lead time before a
disruption crosses a critical threshold.

Because real 30-year labelled corridor-disruption data is not redistributable
here, we synthesise a realistic training corpus from a documented generative
process (tension auto-correlation, sanctions pressure, price momentum, seasonal
incident rate, naval-presence proxy). The model then *learns* the mapping - it
is not hand-coded. This is the prototype of the "GPT-for-energy-security"
foundation model in the roadmap; swap the synthetic corpus for live
GDELT/AIS/sanctions feeds and the same pipeline trains on real data.

Two heads:
  * GradientBoostingClassifier  -> P(disruption within horizon)
  * GradientBoostingRegressor   -> lead time (days) to threshold crossing
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List

import numpy as np
from sklearn.ensemble import (GradientBoostingClassifier,
                              GradientBoostingRegressor)
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from geos import config

FEATURES = [
    "tension",            # 0-1 geopolitical tension index
    "tension_momentum",   # change vs prior period
    "sanctions_pressure", # 0-1
    "price_momentum",     # normalised Brent momentum
    "naval_presence",     # 0-1 military build-up proxy
    "incident_rate",      # recent maritime incidents (rate)
    "season",             # 0-1 seasonal risk (winter demand etc.)
    "base_risk",          # corridor structural base risk
]


@dataclass
class RiskPrediction:
    corridor_id: str
    corridor_name: str
    disruption_probability: float
    lead_time_days: float
    drivers: Dict[str, float]

    def to_dict(self) -> dict:
        return {
            "corridor_id": self.corridor_id,
            "corridor_name": self.corridor_name,
            "disruption_probability": round(self.disruption_probability, 4),
            "lead_time_days": round(self.lead_time_days, 1),
            "top_drivers": dict(sorted(
                self.drivers.items(), key=lambda kv: kv[1], reverse=True)[:3]),
        }


def _generate_corpus(n: int = 6000, seed: int = config.RANDOM_SEED):
    """Synthesise a labelled corpus from a documented generative process."""
    rng = np.random.default_rng(seed)
    X = np.zeros((n, len(FEATURES)))
    y_cls = np.zeros(n, dtype=int)
    y_lead = np.zeros(n)

    for i in range(n):
        tension = rng.beta(2, 5)
        tension_mom = rng.normal(0, 0.15)
        sanctions = rng.beta(2, 6)
        price_mom = rng.normal(0, 1)
        naval = np.clip(tension * 0.6 + rng.normal(0, 0.2), 0, 1)
        incident = np.clip(rng.poisson(1 + tension * 4) / 8.0, 0, 1)
        season = rng.random()
        base_risk = rng.uniform(0.04, 0.30)

        X[i] = [tension, tension_mom, sanctions, price_mom,
                naval, incident, season, base_risk]

        # latent disruption hazard (the "truth" the model must learn)
        logit = (-2.4 + 3.6 * tension + 2.0 * naval + 1.8 * incident
                 + 1.3 * sanctions + 0.7 * max(0, tension_mom) * 3
                 + 2.5 * base_risk + 0.3 * season + 0.15 * price_mom)
        p = 1 / (1 + np.exp(-logit))
        y_cls[i] = rng.random() < p
        # lead time shrinks as hazard rises (more imminent)
        y_lead[i] = np.clip(rng.normal(20 * (1 - p) + 2, 4), 0.5, 45)

    return X, y_cls, y_lead


class GeopoliticalRiskModel:
    """Trained forecaster for corridor disruption probability + lead time."""

    def __init__(self) -> None:
        self.clf = GradientBoostingClassifier(
            n_estimators=120, max_depth=3, learning_rate=0.08,
            random_state=config.RANDOM_SEED)
        self.reg = GradientBoostingRegressor(
            n_estimators=120, max_depth=3, learning_rate=0.08,
            random_state=config.RANDOM_SEED)
        self.auc_: float = 0.0
        self._fit()

    def _fit(self) -> None:
        X, yc, yl = _generate_corpus()
        Xtr, Xte, yctr, ycte = train_test_split(
            X, yc, test_size=0.25, random_state=config.RANDOM_SEED)
        self.clf.fit(Xtr, yctr)
        try:
            self.auc_ = float(roc_auc_score(ycte, self.clf.predict_proba(Xte)[:, 1]))
        except ValueError:
            self.auc_ = 0.0
        self.reg.fit(X, yl)

    def feature_importance(self) -> Dict[str, float]:
        return {f: round(float(w), 4)
                for f, w in zip(FEATURES, self.clf.feature_importances_)}

    def predict(self, feats: Dict[str, float], corridor_id: str = "",
                corridor_name: str = "") -> RiskPrediction:
        x = np.array([[feats.get(f, 0.0) for f in FEATURES]])
        prob = float(self.clf.predict_proba(x)[0, 1])
        lead = float(self.reg.predict(x)[0])
        # per-instance driver attribution = feature value x global importance
        imp = self.clf.feature_importances_
        drivers = {f: round(float(feats.get(f, 0.0) * imp[j]), 4)
                   for j, f in enumerate(FEATURES)}
        return RiskPrediction(corridor_id, corridor_name, prob, lead, drivers)

    def predict_corridors(self, event=None) -> List[RiskPrediction]:
        """Score every corridor given the (optional) active shock event."""
        from geos.data import seed_data as sd
        out = []
        tension = getattr(event, "geopolitical_tension_delta", 0.1) if event else 0.1
        sanctions = getattr(event, "sanctions_pressure", 0.0) if event else 0.0
        affected = set(getattr(event, "affected_corridors", []) if event else [])
        hormuz_p = getattr(event, "hormuz_closure_prob", 0.0) if event else 0.0

        for c in sd.CORRIDORS:
            elevated = c.id in affected
            feats = {
                "tension": min(1.0, tension + (0.3 if elevated else 0.0)),
                "tension_momentum": 0.2 if elevated else 0.0,
                "sanctions_pressure": sanctions,
                "price_momentum": 1.5 if elevated else 0.2,
                "naval_presence": min(1.0, (hormuz_p if c.id == "cor_hormuz" else 0.0)
                                      + (0.4 if elevated else tension * 0.3)),
                "incident_rate": 0.7 if elevated else c.base_risk * 1.5,
                "season": 0.5,
                "base_risk": c.base_risk,
            }
            out.append(self.predict(feats, c.id, c.name))
        out.sort(key=lambda r: r.disruption_probability, reverse=True)
        return out


@lru_cache(maxsize=1)
def get_risk_model() -> GeopoliticalRiskModel:
    """Singleton - trained once at first use."""
    return GeopoliticalRiskModel()
