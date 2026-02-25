"""
normalizer.py — Dynamic per-metric normalization.

Replaces the hard-coded BASE = 3000.0 in the original sim/ metric classes.
Instead of normalising at evaluation time with a fixed constant, we:
  1. Collect all raw observed values for each metric.
  2. Compute a dynamic reference range (max observed value, or a per-metric
     design constraint if defined) at the START of each BO iteration.
  3. Normalise to [0, 1] using that dynamic base.

This approach ensures that BoTorch always operates on well-scaled numbers
regardless of the absolute magnitude of the metrics, and avoids the
saturation problem (values clamped to 1.0) that occurred with BASE = 3000.

Canonical raw metric names and units:
  accuracy   : float, 0.0 ~ 1.0  (no normalisation needed; already bounded)
  energy_uj  : float, uJ
  timing_us  : float, us
  area_mm2   : float, mm^2
"""

from __future__ import annotations

from typing import Dict, List, Optional


class DynamicNormalizer:
    """
    Maintains running statistics over observed metric values and provides
    a consistent normalisation function for the BO engine.

    Usage:
        normalizer = DynamicNormalizer(constraints)
        # After each evaluation, register the raw values:
        normalizer.update({"energy_uj": 1234.5, "timing_us": 88.0, "area_mm2": 0.42})
        # Before passing to Ax, normalise:
        normed = normalizer.normalize({"accuracy": 0.91, "energy_uj": 1234.5, ...})
    """

    METRIC_KEYS = ("energy_uj", "timing_us", "area_mm2")

    def __init__(
        self,
        upper_bound_constraints: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Args:
            upper_bound_constraints:  Optional dict with design-space upper bounds
                for each metric in raw units, e.g.:
                {"energy_uj": 5000.0, "timing_us": 200.0, "area_mm2": 2.0}
                When provided, these are used as the initial BASE even before any
                data is observed, preventing divide-by-zero on the first iteration.
        """
        self._observations: Dict[str, List[float]] = {k: [] for k in self.METRIC_KEYS}
        self._constraints: Dict[str, float] = upper_bound_constraints or {}

    def update(self, raw_metrics: Dict[str, float]) -> None:
        """Register a new set of raw metric observations."""
        for key in self.METRIC_KEYS:
            if key in raw_metrics:
                self._observations[key].append(raw_metrics[key])

    def _get_base(self, key: str) -> float:
        """
        Compute the normalisation base for a given metric.

        Priority:
          1. max(observed values) if any observations exist.
          2. User-provided constraint upper bound.
          3. Fallback = 1.0 (identity normalisation, logs a warning).
        """
        obs = self._observations.get(key, [])
        if obs:
            return max(obs)
        if key in self._constraints:
            return self._constraints[key]
        # No data and no constraint — return 1.0 to avoid division errors
        return 1.0

    def normalize(self, raw_metrics: Dict[str, float]) -> Dict[str, float]:
        """
        Normalise raw metric values to approximately [0, 1].

        `accuracy` is passed through unchanged (already 0~1).
        Other metrics are divided by their dynamic base and clamped to [0, 1].

        Returns:
            A new dict with the same keys but normalised float values.
        """
        normed: Dict[str, float] = {}

        # Accuracy: pass through
        if "accuracy" in raw_metrics:
            normed["accuracy"] = float(raw_metrics["accuracy"])

        # Other metrics: dynamic normalisation
        for key in self.METRIC_KEYS:
            if key not in raw_metrics:
                continue
            base = self._get_base(key)
            value = float(raw_metrics[key])
            normed[key] = min(value / base, 1.0)  # clamp to 1.0 max

        return normed

    def denormalize(self, normed_metrics: Dict[str, float]) -> Dict[str, float]:
        """
        Reverse the normalisation to recover approximate raw values.
        Useful for logging or Cross-Path Calibration.
        """
        raw: Dict[str, float] = {}
        if "accuracy" in normed_metrics:
            raw["accuracy"] = normed_metrics["accuracy"]
        for key in self.METRIC_KEYS:
            if key not in normed_metrics:
                continue
            base = self._get_base(key)
            raw[key] = normed_metrics[key] * base
        return raw

    @property
    def current_bases(self) -> Dict[str, float]:
        """Return the current normalisation bases for inspection/logging."""
        return {k: self._get_base(k) for k in self.METRIC_KEYS}
