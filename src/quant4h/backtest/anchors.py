"""AŞAMA 7 — stop anchor KARŞILAŞTIRMASI (SEÇİM YOK; seçim yalnız Aşama 9, OOS).

Anchor'lar (kullanıcı şartnamesi 2026-09-17):
  * **A0** — onaylı swing ± buffer **1.0×ATR** (Aşama 6'da kullanılan MEVCUT stop;
    frame'e DOKUNULMAZ, no-op).
  * **A1** — Donchian(20) **ters bandı**: long stop = `donchian_low`, short stop =
    `donchian_high` (buffer YOK).
  * **A2** — onaylı swing ± buffer **0.5×ATR**: `levels.add_structural_stop`
    `buffer_atr=0.5` ile YENİDEN kullanılır (0.5 kilitli aday kümesi
    {0.5, 1.0, 1.5} içindedir; küme dışı değer orada zaten ValueError).

Kurallar (Aşama 3/6 sözleşmeleriyle aynı):
  * Override frame KOPYASINA yazılır; girdi frame değişmez (non-destructive).
  * Geçerlilik: stop sonlu, >0 ve close'a göre DOĞRU tarafta (long: stop < close,
    short: stop > close). Değilse `stop_valid_* = False` → fail-closed (H35:
    geçerli stopu olmayan pozisyon ASLA açılmaz).
  * Nedensellik: `donchian_high/low` Aşama 3'te "son N KAPANMIŞ bar" üzerinden
    shift'li; swing'ler k+1 onay gecikmeli. Anchor override YENİ look-ahead
    getirmez; sinyal zinciri (stop_valid kapısı + pozisyon vekili) override
    SONRASI çalıştırıldığı için proxy de aynı stop'u kullanır.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

ANCHORS = ("A0", "A1", "A2")


def apply_anchor(df: pd.DataFrame, anchor: str, *,
                 allow_short: Optional[bool] = None) -> pd.DataFrame:
    """Stop kolonlarını anchor'a göre yeniden yaz (kopya üzerinde)."""
    if anchor not in ANCHORS:
        raise ValueError(f"anchor '{anchor}' aday kümesinde değil: {ANCHORS}. "
                         f"Anchor/buffer SEÇİMİ yalnızca Aşama 9'da, OOS yapılır.")
    out = df.copy()
    if anchor == "A0":
        return out                                   # mevcut Aşama 3 stop'ları
    if anchor == "A2":
        from ..features.levels import add_structural_stop
        return add_structural_stop(out, allow_short=allow_short, buffer_atr=0.5)

    # ---- A1: Donchian(20) ters bandı ----
    if "donchian_low" not in out.columns or "donchian_high" not in out.columns:
        raise ValueError("A1 anchor'ı donchian_high/donchian_low kolonları gerektirir "
                         "(önce Aşama 3 levels frame'i üretin)")
    close = pd.to_numeric(out["close"], errors="coerce")
    atr = pd.to_numeric(out.get("atr"), errors="coerce")
    atr_ok = atr.notna() & (atr > 0)
    dl = pd.to_numeric(out["donchian_low"], errors="coerce")
    dh = pd.to_numeric(out["donchian_high"], errors="coerce")

    valid_l = dl.notna() & (dl > 0) & close.notna() & (close > 0) & (dl < close)
    out["stop_long"] = dl.where(valid_l).to_numpy()
    out["stop_long_dist"] = (close - dl).where(valid_l).to_numpy()
    out["stop_long_atr_mult"] = ((close - dl) / atr).where(valid_l & atr_ok).to_numpy()
    out["stop_long_pct_price"] = ((close - dl) / close * 100.0).where(valid_l).to_numpy()
    out["stop_valid_long"] = valid_l.fillna(False).to_numpy()
    out["stop_anchor_long"] = np.where(valid_l, "donchian20_low", "")

    short_ok = allow_short if allow_short is not None else True
    if short_ok:
        valid_s = dh.notna() & (dh > 0) & close.notna() & (close > 0) & (dh > close)
        out["stop_short"] = dh.where(valid_s).to_numpy()
        out["stop_short_dist"] = (dh - close).where(valid_s).to_numpy()
        out["stop_short_atr_mult"] = ((dh - close) / atr).where(valid_s & atr_ok).to_numpy()
        out["stop_short_pct_price"] = ((dh - close) / close * 100.0).where(valid_s).to_numpy()
        out["stop_valid_short"] = valid_s.fillna(False).to_numpy()
        out["stop_anchor_short"] = np.where(valid_s, "donchian20_high", "")
    return out


__all__ = ["ANCHORS", "apply_anchor"]
