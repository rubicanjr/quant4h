"""AŞAMA 5 — Giriş tetiği ve sinyal montajı.

YENİ İNDİKATÖR YOK. Tetik, Aşama 3'te zaten üretilen Donchian(20) seviyesidir.

1) TETİK (kabul kriteri 1)
--------------------------
    LONG  : close[t] > max(high[t-20 .. t-1])
    SHORT : close[t] < min(low[t-20 .. t-1])      (yalnız CORE varlıklar)

Yani "önceki 20 **KAPANMIŞ** barın en yükseği". Mevcut bar kendi zirvesiyle
karşılaştırılmaz; karşılaştırmada kullanılan pencere bar `t-1`'de biter.

**SHIFT SAYISI HAKKINDA AÇIK NOT (önemli):**
`levels.add_donchian()` zaten `rolling(20).max().shift(1)` hesaplar; yani
`donchian_high[t] = max(high[t-20..t-1])`. Kullanıcı şartnamesindeki
"donchian_high_20.shift(1)" ifadesi **anlam olarak** budur. Bu modül bu yüzden
`donchian_high` üzerine İKİNCİ bir `shift(1)` **UYGULAMAZ** — uygulansa pencere
21 bara çıkar ve "önceki 20 kapanmış bar" kriteri bozulur. Eşdeğerlik
`tests/test_signals.py::test_trigger_equals_manual_20_bar_breakout` içinde
ham high/low serisinden elle hesaplanarak kilitlenmiştir.

2) ZİNCİR (kabul kriteri 2)
---------------------------
    long_signal_raw = regime_ok ∧ context_ok(XU030, yalnız BIST) ∧ tradable
                      ∧ return_valid ∧ momentum_ok ∧ trigger_ok
                      ∧ stop_valid_long        << EK HALKA, bkz. aşağıda

`stop_valid_long` halkası **fail-closed** ilkesi gereği EKLENMİŞTİR: Aşama 3'te
stop girişten önce belirlenir ve dondurulur; dondurulacak bir stop YOKSA
pozisyon açılamaz, dolayısıyla sinyal de üretilemez. Kullanıcı şartnamesindeki
listede açıkça yazmıyordu; bu bir tasarım kararıdır ve rapor + PROGRESS'te
açıkça işaretlenmiştir. Kaldırmak için `require_valid_stop=False` verilebilir.

3) İCRA ZAMANI (kabul kriteri 3) — KRİTİK
------------------------------------------
Sinyal bar `t`'nin KAPANIŞINDA üretilir. İşlem **bar t+1'in AÇILIŞINDA**
gerçekleşir. Buna göre:

    signal_bar      = t          (kararın verildiği, KAPANMIŞ bar)
    signal_close    = close[t]   (karar fiyatı; P&L'de KULLANILMAZ)
    execution_bar   = t+1
    execution_price = open[t+1]  (GERÇEK giriş fiyatı)

`t+1` barı henüz YOKSA (serinin sonu) `execution_bar = -1` ve
`execution_price = NaN` olur: **uygulanamaz sinyal**. Bu tek kural, backtest'te
"kapanışta gir" varsayımının yarattığı hayali performansı engeller.

4) COOLDOWN ve POZİSYON FARKINDALIKLI BASKILAMA (kabul kriteri 4)
-----------------------------------------------------------------
Aynı varlıkta sinyal spam'i engellenir. İki kural birlikte çalışır:

* **Pozisyon açıkken yeni sinyal YOK.** Pozisyon durumu, Aşama 6/7'nin tam
  motoru henüz yazılmadığı için burada **basit bir vekil** ile izlenir: giriş
  yapıldıktan sonra, DONDURULMUŞ yapısal stop'un bar içi (high/low) ihlal
  edildiği ilk barda pozisyon kapanmış SAYILIR. Bu bir VEKİLDİR; kâr alma,
  time-stop ve trailing Aşama 7'de eklendiğinde gerçek motorla değiştirilecek.
  Vekilin yanlılığı bilinçli olarak TEK YÖNLÜDÜR: gerçek sistemde pozisyon
  daha erken de kapanabilir (TP), yani vekil daha AZ sinyal üretir.

* **Cooldown.** Pozisyon kapandıktan sonra `cooldown_bars` bar boyunca yeni
  sinyal bastırılır.

**OFF-BY-ONE SÖZLEŞMESİ (açıkça belgelendi):** `cooldown_bars = 3` iken bir
sinyal/pozisyon olayından sonra **3 bar sessizlik** gerekir; yani olay barı `s`
ise yeniden sinyal üretebilecek ilk bar `s + 4`'tür (12 saatlik bekleme, 4 saat
× 3). Kullanıcının "minimum 3 bar (12 saat)" ifadesi bu şekilde yorumlandı.
Farklı bir yorum istenirse `cooldown_bars` değiştirilir; kural tek yerde ve
test edilmiştir.

Bu döngü **nedenseldir**: bar `t`'deki karar yalnızca `t-1` ve öncesine
bağlıdır (pozisyon durumu geçmişten gelir, cooldown geçmişten gelir). Gelecek
bilgi kullanılmaz; `tests/test_signals.py` silme testiyle kilitler.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import DEFAULT_LEVELS, DEFAULT_MOMENTUM, LevelsConfig, MomentumConfig

TRIGGER_COLUMNS = (
    "dc_high_prev20",        # max(high[t-20..t-1]) — mevcut bar HARİÇ
    "dc_low_prev20",         # min(low[t-20..t-1])
    "dc_prev20_valid_frac",  # penceredeki anchor-uygun bar oranı
    "trigger_long",
    "trigger_short",
)

SIGNAL_COLUMNS = (
    "long_signal_raw",       # zincir (cooldown ÖNCESİ)
    "long_signal",           # cooldown + pozisyon baskılaması SONRASI
    "short_signal_raw",
    "short_signal",
    "suppressed_by_position",
    "suppressed_by_cooldown",
    "position_open",         # vekil pozisyon durumu (0/1)
    "entry_stop",            # açık pozisyonun DONDURULMUŞ stop'u
    "signal_bar_close",      # karar fiyatı (P&L'de KULLANILMAZ)
    "execution_bar",         # t+1 konumu; -1 ise UYGULANAMAZ
    "execution_price",       # open[t+1] = GERÇEK giriş fiyatı
    "execution_timestamp_utc",
    "execution_valid",
    "signal_side",           # "" | "long" | "short"
)

DEFAULT_COOLDOWN_BARS = 3        # = 12 saat (4H bar)


# --------------------------------------------------------------------------
# 1. tetik
# --------------------------------------------------------------------------

def add_trigger(df: pd.DataFrame, period: int = 20,
                use_anchor_ok: bool = True,
                min_valid_frac: float = 0.90) -> pd.DataFrame:
    """Donchian(period) breakout trigger. No new indicator, no second shift."""
    if period < 2:
        raise ValueError("period >= 2 olmali")
    out = df.copy()
    high = pd.to_numeric(out["high"], errors="coerce").astype("float64")
    low = pd.to_numeric(out["low"], errors="coerce").astype("float64")
    close = pd.to_numeric(out["close"], errors="coerce").astype("float64")

    if use_anchor_ok and "anchor_ok" in out.columns:
        elig = out["anchor_ok"].astype(bool)
    elif "non_tradable" in out.columns or "return_valid" in out.columns:
        from ..features.levels import anchor_eligible
        elig = anchor_eligible(out)
    else:
        elig = pd.Series(True, index=out.index)
    # anchor uygunluğunu frame'e de yaz: hem denetlenebilir olsun hem de
    # downstream (rapor/test) yeniden hesaplamak zorunda kalmasın.
    if "anchor_ok" not in out.columns:
        out["anchor_ok"] = elig.to_numpy()

    hm = high.where(elig)
    lm = low.where(elig)
    e = elig.to_numpy(dtype="float64")
    # shift(1): pencere bar t-1'de BİTER, mevcut bar pencereye GİRMEZ
    dch = hm.rolling(period, min_periods=1).max().shift(1)
    dcl = lm.rolling(period, min_periods=1).min().shift(1)
    cnt = pd.Series(e, index=out.index).rolling(period, min_periods=1).sum().shift(1)
    frac = (cnt / float(period)).to_numpy(dtype="float64")
    enough = np.isfinite(frac) & (frac >= min_valid_frac)

    out["dc_high_prev20"] = np.where(enough, dch.to_numpy(dtype="float64"), np.nan)
    out["dc_low_prev20"] = np.where(enough, dcl.to_numpy(dtype="float64"), np.nan)
    out["dc_prev20_valid_frac"] = frac
    out["trigger_long"] = (close > out["dc_high_prev20"]).fillna(False).to_numpy()
    out["trigger_short"] = (close < out["dc_low_prev20"]).fillna(False).to_numpy()
    # anchor kısıtıyla tutarlılık: bayraklı barda tetik ÜRETİLMEZ
    bad = ~elig
    out.loc[bad, "trigger_long"] = False
    out.loc[bad, "trigger_short"] = False
    out.attrs["trigger_period"] = period
    return out


# --------------------------------------------------------------------------
# 2. zincir
# --------------------------------------------------------------------------

LONG_CHAIN_V2: Tuple[Tuple[str, str], ...] = (
    ("regime",       "long_regime_ok"),
    ("context",      "longs_allowed"),
    ("tradable",     "~non_tradable"),
    ("return_valid", "return_valid"),
    ("momentum",     "momentum_ok"),
    ("trigger",      "trigger_long"),
    ("stop_valid",   "stop_valid_long"),      # EK halka: fail-closed (bkz. docstring)
)
SHORT_CHAIN_V2: Tuple[Tuple[str, str], ...] = (
    ("regime",       "short_regime_ok"),
    ("tradable",     "~non_tradable"),
    ("return_valid", "return_valid"),
    ("momentum",     "momentum_short_ok"),
    ("trigger",      "trigger_short"),
    ("stop_valid",   "stop_valid_short"),
)


def _gate(out: pd.DataFrame, col: str) -> pd.Series:
    if col == "~non_tradable":
        if "non_tradable" not in out.columns:
            return pd.Series(True, index=out.index, dtype=bool)
        return ~pd.to_numeric(out["non_tradable"], errors="coerce").fillna(True).astype(bool)
    if col not in out.columns:
        return pd.Series(False, index=out.index, dtype=bool)     # fail-closed
    s = out[col]
    if s.dtype == bool:
        return s
    return pd.to_numeric(s, errors="coerce").fillna(False).astype(bool)


def add_signal_chain_v2(df: pd.DataFrame, is_stock: bool = False,
                        require_valid_stop: bool = True,
                        allow_short: Optional[bool] = None) -> pd.DataFrame:
    """Raw signal chain (BEFORE cooldown). Reports every link's bar count."""
    out = df.copy()
    short_allowed = (not is_stock) if allow_short is None else bool(allow_short)

    acc = pd.Series(True, index=out.index, dtype=bool)
    counts: Dict[str, int] = {}
    for label, col in LONG_CHAIN_V2:
        if label == "context" and not is_stock:
            counts["context"] = None            # core varlıkta bağlam kapısı YOK
            continue
        if label == "stop_valid" and not require_valid_stop:
            counts["stop_valid"] = int(acc.sum())
            continue
        acc = acc & _gate(out, col)
        counts[label] = int(acc.sum())
    out["long_signal_raw"] = acc.to_numpy()
    out.attrs["long_chain_counts"] = counts

    if short_allowed:
        accs = pd.Series(True, index=out.index, dtype=bool)
        sc: Dict[str, int] = {}
        for label, col in SHORT_CHAIN_V2:
            if label == "stop_valid" and not require_valid_stop:
                sc["stop_valid"] = int(accs.sum())
                continue
            accs = accs & _gate(out, col)
            sc[label] = int(accs.sum())
        out["short_signal_raw"] = accs.to_numpy()
        out.attrs["short_chain_counts"] = sc
    else:
        out["short_signal_raw"] = False
        out.attrs["short_chain_counts"] = {}
    return out


# --------------------------------------------------------------------------
# 3+4. cooldown + pozisyon farkındalıklı bastırma + icra zamanı
# --------------------------------------------------------------------------

def apply_cooldown_and_execution(df: pd.DataFrame,
                                 cooldown_bars: int = DEFAULT_COOLDOWN_BARS,
                                 cooldown_counts_from: str = "entry_bar",
                                 position_exit_proxy: str = "frozen_stop_intrabar",
                                 max_position_bars: Optional[int] = None,
                                 is_stock: bool = False,
                                 allow_short: Optional[bool] = None) -> pd.DataFrame:
    """Single causal pass: position proxy -> cooldown -> execution timing.

    Bar t'deki karar yalnızca t-1 ve öncesine bağlıdır. Döngü içinde ileriye
    bakılmaz; ``execution_*`` alanları `shift(-1)` ile üretilir ve son barda
    bilinçli olarak NaN/-1 kalır (uygulanamaz sinyal).
    """
    if cooldown_counts_from not in ("entry_bar", "signal_bar", "exit_bar"):
        raise ValueError(f"cooldown_counts_from geçersiz: {cooldown_counts_from}")
    if cooldown_bars < 0:
        raise ValueError("cooldown_bars >= 0 olmali")
    if position_exit_proxy not in ("frozen_stop_intrabar", "none"):
        raise ValueError(f"position_exit_proxy geçersiz: {position_exit_proxy!r} "
                         f"('frozen_stop_intrabar' = kullanıcı kuralı, 'none' = yalnız cooldown)")
    if max_position_bars is not None and max_position_bars < 1:
        raise ValueError("max_position_bars >= 1 olmali")
    out = df.copy()
    short_allowed = (not is_stock) if allow_short is None else bool(allow_short)
    n = len(out)

    close = pd.to_numeric(out["close"], errors="coerce").to_numpy(dtype="float64")
    high = pd.to_numeric(out["high"], errors="coerce").to_numpy(dtype="float64")
    low = pd.to_numeric(out["low"], errors="coerce").to_numpy(dtype="float64")
    open_ = pd.to_numeric(out["open"], errors="coerce").to_numpy(dtype="float64")
    stop_l = (pd.to_numeric(out["stop_long"], errors="coerce").to_numpy(dtype="float64")
              if "stop_long" in out.columns else np.full(n, np.nan))
    stop_s = (pd.to_numeric(out["stop_short"], errors="coerce").to_numpy(dtype="float64")
              if "stop_short" in out.columns else np.full(n, np.nan))
    raw_l = out["long_signal_raw"].to_numpy(dtype=bool) if "long_signal_raw" in out.columns \
        else np.zeros(n, dtype=bool)
    raw_s = out["short_signal_raw"].to_numpy(dtype=bool) if "short_signal_raw" in out.columns \
        else np.zeros(n, dtype=bool)
    if not short_allowed:
        raw_s = np.zeros(n, dtype=bool)

    sig = np.zeros(n, dtype=bool)
    supp_pos = np.zeros(n, dtype=bool)
    supp_cool = np.zeros(n, dtype=bool)
    pos_open = np.zeros(n, dtype=np.int8)
    entry_stop = np.full(n, np.nan)
    cur_stop_arr = np.full(n, np.nan)
    side = np.array([""] * n, dtype=object)

    in_pos = False
    cur_stop = np.nan
    cur_side = ""
    entry_bar = -1
    # resume_at: sinyal üretebilecek İLK bar konumu (t < resume_at ise bastırılır).
    # Bu gösterim off-by-one hatasını yapısal olarak imkânsız kılar.
    resume_at = 0

    for t in range(n):
        # (a) açık pozisyon var mı? vekil çıkış: DONDURULMUŞ stop'un bar içi ihlali
        if in_pos:
            exited = False
            if position_exit_proxy == "frozen_stop_intrabar" and np.isfinite(cur_stop):
                exited = bool((low[t] <= cur_stop) if cur_side == "long"
                              else (high[t] >= cur_stop))
            if not exited and max_position_bars is not None:
                # ZORUNLU time-stop (Aşama 7'de gerçek time-stop ile değiştirilecek).
                # Sebep: yapısal stop çok genişse (~2.6 ATR geride) fiyat onu 9 YIL
                # boyunca ihlal etmeyebiliyor ve pozisyon sonsuza dek açık kalıp
                # TÜM sinyalleri bastırıyor (ölçüldü: BTC 592 ham -> 3 final).
                exited = (t - entry_bar) >= int(max_position_bars)
            if exited:
                in_pos = False
                if cooldown_counts_from == "exit_bar":
                    resume_at = max(resume_at, t + 1 + cooldown_bars)
        pos_open[t] = 1 if in_pos else 0

        # (b) ham sinyal var mı ve bastırılmalı mı?
        want_long = bool(raw_l[t])
        want_short = bool(raw_s[t])
        if want_long or want_short:
            if in_pos:
                supp_pos[t] = True                      # pozisyon açıkken sinyal YOK
            elif t < resume_at:
                supp_cool[t] = True                     # cooldown
            else:
                sig[t] = True
                cur_side = "long" if want_long else "short"
                side[t] = cur_side
                cur_stop = stop_l[t] if cur_side == "long" else stop_s[t]
                cur_stop_arr[t] = cur_stop
                entry_stop[t] = cur_stop
                if not np.isfinite(cur_stop):
                    # Dondurulacak stop YOKSA pozisyon AÇILMAZ (fail-closed).
                    sig[t] = False
                    side[t] = ""
                    cur_side = ""
                    supp_pos[t] = True
                else:
                    in_pos = True
                    entry_bar = t + 1
                # giriş barı = t+1 (bir sonraki barın AÇILIŞI). cooldown bu bardan
                # itibaren cooldown_bars kadar sürer -> ilk uygun bar (t+1)+cooldown_bars.
                if cooldown_counts_from == "entry_bar":
                    resume_at = max(resume_at, (t + 1) + cooldown_bars)
                elif cooldown_counts_from == "signal_bar":
                    resume_at = max(resume_at, t + cooldown_bars)
                # "exit_bar" modunda resume_at yalnızca çıkışta güncellenir
                if position_exit_proxy == "none":
                    # Pozisyon takibi YOK: kullanıcı kuralının "yalnız cooldown"
                    # varyantı. Pozisyon sonsuza dek açık kalsaydı tek bir sinyal
                    # üretilir ve cooldown hiç test edilemezdi (bulunan kusur).
                    in_pos = False
                    cur_stop = np.nan
                    cur_side = ""

    out["long_signal"] = sig & (side == "long")
    out["short_signal"] = sig & (side == "short")
    out["signal_side"] = side
    out["suppressed_by_position"] = supp_pos
    out["suppressed_by_cooldown"] = supp_cool
    # entry_stop, pozisyonun açık olduğu barlarda VE pozisyonun açıldığı sinyal
    # barında dolu olmalıdır (aksi hâlde sinyal barında NaN görünür ve
    # "stop girişten önce bellidir" denetimi yapılamaz).
    entry_stop_series = pd.Series(entry_stop, index=out.index)
    entry_stop_series[(out["long_signal"] | out["short_signal"]).to_numpy()] = \
        pd.Series(cur_stop_arr, index=out.index)[
            (out["long_signal"] | out["short_signal"]).to_numpy()]
    out["position_open"] = pos_open
    out["entry_stop"] = entry_stop_series.to_numpy()

    # ---- icra zamanı: BİR SONRAKİ BARIN AÇILIŞI ----
    sig_any = out["long_signal"] | out["short_signal"]
    out["signal_bar_close"] = np.where(sig_any, close, np.nan)
    nxt_open = pd.Series(open_, index=out.index).shift(-1).to_numpy()
    nxt_ts = pd.Series(pd.to_datetime(out["timestamp_utc"], utc=True),
                       index=out.index).shift(-1)
    exec_bar = np.full(n, -1, dtype="int64")
    idx = np.arange(n)
    exec_bar[:-1] = idx[:-1] + 1
    out["execution_bar"] = np.where(sig_any, exec_bar, -1)
    out["execution_price"] = np.where(sig_any, nxt_open, np.nan)
    # tz BİLİNÇLİ tutulmalı: np.where(datetime64[ns]) tz'yi düşürür ve
    # `execution_timestamp_utc == timestamp_utc[t+1]` karşılaştırması patlar.
    exec_ts = nxt_ts.where(pd.Series(sig_any, index=out.index))
    out["execution_timestamp_utc"] = exec_ts
    # son barda sinyal olsa bile t+1 YOK -> uygulanamaz
    last = n - 1
    if n and sig_any[last]:
        out.loc[out.index[last], "execution_valid"] = False
        out.loc[out.index[last], "execution_price"] = np.nan
        out.loc[out.index[last], "execution_bar"] = -1
    valid_exec = (sig_any.to_numpy() & np.isfinite(out["execution_price"].to_numpy(dtype="float64"))
                  & (out["execution_bar"].to_numpy() >= 0))
    if "execution_valid" in out.columns:
        out["execution_valid"] = (out["execution_valid"].astype(bool) & valid_exec)
    else:
        out["execution_valid"] = valid_exec

    out.attrs["signal_engine"] = {
        "cooldown_bars": int(cooldown_bars),
        "cooldown_counts_from": cooldown_counts_from,
        "cooldown_semantics": "cooldown_bars=3, cooldown_counts_from='entry_bar': "
                              "sinyal barı s ise giriş barı s+1'dir ve ilk YENİDEN sinyal "
                              "üretebilen bar (s+1)+3 = s+4'tür. Yani girişten sonra 3 bar "
                              "(12 saat) sessizlik. Off-by-one sözleşmesi budur ve "
                              "test_cooldown_off_by_one_is_exactly_as_documented ile kilitlidir.",
        "position_exit_proxy": position_exit_proxy,
        "max_position_bars": max_position_bars,
        "position_exit_proxy_note": "VEKİLDİR: Aşama 6/7'nin gerçek motoru (TP, time-stop, "
                                    "trailing) gelene kadar yalnızca DONDURULMUŞ stop'un "
                                    "bar içi ihlali çıkış sayılır. Yanlılık TEK YÖNLÜDÜR: "
                                    "gerçek sistemde pozisyon daha erken kapanabilir, yani "
                                    "vekil DAHA AZ sinyal üretir.",
        "execution_rule": "sinyal bar t KAPANIŞINDA üretilir; giriş bar t+1 AÇILIŞINDA. "
                          "signal_bar_close P&L'de KULLANILMAZ.",
        "unexecutable_signals": int((sig_any.to_numpy() & ~out["execution_valid"].to_numpy()).sum()),
        "require_valid_stop": True,
    }
    return out


def build_signals(df: pd.DataFrame, is_stock: bool = False,
                  cooldown_bars: int = DEFAULT_COOLDOWN_BARS,
                  trigger_period: int = 20,
                  require_valid_stop: bool = True,
                  allow_short: Optional[bool] = None,
                  cooldown_counts_from: str = "entry_bar",
                  position_exit_proxy: str = "frozen_stop_intrabar",
                  max_position_bars: Optional[int] = None) -> pd.DataFrame:
    """Full Aşama 5 pass: trigger -> chain -> cooldown -> execution timing."""
    out = add_trigger(df, period=trigger_period)
    out = add_signal_chain_v2(out, is_stock=is_stock,
                              require_valid_stop=require_valid_stop,
                              allow_short=allow_short)
    out = apply_cooldown_and_execution(out, cooldown_bars=cooldown_bars,
                                       cooldown_counts_from=cooldown_counts_from,
                                       position_exit_proxy=position_exit_proxy,
                                       max_position_bars=max_position_bars,
                                       is_stock=is_stock, allow_short=allow_short)
    return out


# --------------------------------------------------------------------------
# rapor yardımcıları
# --------------------------------------------------------------------------

def signal_stats(df: pd.DataFrame, timeframe: str = "4h") -> Dict[str, Any]:
    """Kabul kriteri 5: toplam sinyal, yıllara göre dağılım, ort. sinyaller arası gün."""
    n = len(df)
    hours_per_bar = 4 if timeframe == "4h" else float(timeframe_minutes(timeframe)) / 60.0
    res: Dict[str, Any] = {"bars": n}
    for side in ("long", "short"):
        col = f"{side}_signal"
        if col not in df.columns:
            continue
        m = df[col].astype(bool)
        ts = pd.to_datetime(df.loc[m, "timestamp_utc"], utc=True)
        res[f"{side}_signals"] = int(m.sum())
        res[f"{side}_signal_frac"] = round(float(m.mean()), 5) if n else 0.0
        res[f"{side}_raw_signals"] = int(df[f"{side}_signal_raw"].astype(bool).sum()) \
            if f"{side}_signal_raw" in df.columns else None
        res[f"{side}_suppressed_by_position"] = int(df["suppressed_by_position"].sum()) \
            if "suppressed_by_position" in df.columns else None
        # suppressed_* kolonları yön ayrımı yapmaz (tek döngü var); bu yüzden
        # her iki yönde de aynı toplam raporlanır ve bu açıkça belirtilir.
        res[f"{side}_suppressed_by_cooldown"] = int(df["suppressed_by_cooldown"].sum()) \
            if "suppressed_by_cooldown" in df.columns else None
        if len(ts):
            by_year = ts.dt.year.value_counts().sort_index()
            res[f"{side}_by_year"] = {int(k): int(v) for k, v in by_year.items()}
            srt = ts.sort_values()
            gaps_days = srt.diff().dt.total_seconds().div(86400).dropna()
            res[f"{side}_mean_gap_days"] = round(float(gaps_days.mean()), 2) if len(gaps_days) else None
            res[f"{side}_median_gap_days"] = round(float(gaps_days.median()), 2) if len(gaps_days) else None
            res[f"{side}_min_gap_days"] = round(float(gaps_days.min()), 2) if len(gaps_days) else None
            res[f"{side}_max_gap_days"] = round(float(gaps_days.max()), 2) if len(gaps_days) else None
            res[f"{side}_first"] = str(srt.iloc[0])
            res[f"{side}_last"] = str(srt.iloc[-1])
            span_days = float((srt.iloc[-1] - srt.iloc[0]).days)
            res[f"{side}_signals_per_year"] = (
                round(float(len(srt)) / (span_days / 365.25), 1) if span_days > 0 else None)
        else:
            res[f"{side}_by_year"] = {}
            for k in ("mean_gap_days", "median_gap_days", "min_gap_days", "max_gap_days",
                      "signals_per_year"):
                res[f"{side}_{k}"] = None
        if "execution_valid" in df.columns:
            res[f"{side}_executable"] = int((m & df["execution_valid"].astype(bool)).sum())
            res[f"{side}_unexecutable"] = int((m & ~df["execution_valid"].astype(bool)).sum())
    # cooldown doğrulaması: iki sinyal arası en az kaç bar?
    anysig = ((df["long_signal"].astype(bool) if "long_signal" in df.columns else False) |
              (df["short_signal"].astype(bool) if "short_signal" in df.columns else False))
    pos = np.flatnonzero(anysig.to_numpy())
    if "stop_valid_long" in df.columns and "long_signal_raw" in df.columns:
        res["long_raw_without_valid_stop"] = int(
            (df["long_signal_raw"].astype(bool) & ~df["stop_valid_long"].astype(bool)).sum())
    res["min_signal_gap_bars"] = int(np.diff(pos).min()) if len(pos) > 1 else None
    res["position_open_bars"] = int(df["position_open"].sum()) if "position_open" in df.columns else None
    res["position_open_frac"] = round(float(df["position_open"].mean()), 4) \
        if "position_open" in df.columns and n else None
    return res


def timeframe_minutes(tf: str) -> int:
    from ..data.resample import timeframe_minutes as _f
    return _f(tf)


__all__ = ["add_trigger", "add_signal_chain_v2", "apply_cooldown_and_execution",
           "build_signals", "signal_stats", "LONG_CHAIN_V2", "SHORT_CHAIN_V2",
           "TRIGGER_COLUMNS", "SIGNAL_COLUMNS", "DEFAULT_COOLDOWN_BARS"]
