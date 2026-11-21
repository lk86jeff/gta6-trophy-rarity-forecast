"""GTA VI trophy rarity forecaster (standard library only).

For each trophy: take the distinct Exophase reads (a read counts only when the page changed), fit the trophy's
logit earn rate against log time since the rolling launch with a robust Theil-Sen slope over the recent window,
shrink that slope toward its tier's pooled slope, damp it, and extrapolate to the target. The spread combines a
base drift, the size of the extrapolated move, the fit's residual scatter and the count noise of a small earner
count, all on the logit scale.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
ORIGIN = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
WINDOW_H = 30.0
SHRINK = 0.5
DAMP = 0.45
MAX_MOVE = 1.0


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def hours(s: str) -> float:
    return max(1.0, (ts(s) - ORIGIN.timestamp()) / 3600)


def clamp(x: float) -> float:
    return min(99.99, max(0.01, x))


def logit(p: float) -> float:
    p = clamp(p)
    return math.log(p / (100 - p))


def inv(y: float) -> float:
    return 100 / (1 + math.exp(-y))


def round4(x: float):
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    v = whole / 10000
    return int(v) if v.is_integer() else v


def median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def distinct(history):
    out = []
    for h in history:
        key = (h.get("players_tracked"), tuple(h["rates"]))
        if not out or out[-1][0] != key:
            out.append((key, h))
    return [h for _, h in out]


def theil_sen(xs, ys):
    sl = [(ys[j] - ys[i]) / (xs[j] - xs[i]) for i in range(len(xs)) for j in range(i + 1, len(xs)) if xs[j] - xs[i] > 1e-9]
    if not sl:
        return 0.0, 0.0
    b = median(sl)
    a = median([y - b * x for x, y in zip(xs, ys)])
    res = median([abs(y - (a + b * x)) for x, y in zip(xs, ys)]) * 1.4826
    return b, res


def forecast_case(case: dict) -> dict:
    trophies = case["trophies"]
    reads = distinct(case["history"])
    last = case["history"][-1]
    now_x = math.log(hours(case["at"]))
    tgt_x = math.log(hours(case["target"]))
    dx = tgt_x - now_x
    cut = ts(case["at"]) - WINDOW_H * 3600
    win = [h for h in reads if ts(h["at"]) >= cut]
    if len(win) < 3:
        win = reads[-6:]
    players = last.get("players_tracked") or 0
    fits = []
    for i, _ in enumerate(trophies):
        pts = [(math.log(hours(h["at"])), logit(h["rates"][i])) for h in win if h["rates"][i] is not None]
        if len(pts) >= 2:
            b, res = theil_sen([p[0] for p in pts], [p[1] for p in pts])
        else:
            b, res = 0.0, 0.0
        fits.append((b, res, len(pts)))
    pool = {}
    for t, (b, _, n) in zip(trophies, fits):
        if n >= 2:
            pool.setdefault(t["tier"], []).append(b)
    pooled = {k: median(v) for k, v in pool.items()}
    rows = []
    for i, t in enumerate(trophies):
        r = last["rates"][i]
        if r is None:
            r = next((h["rates"][i] for h in reversed(case["history"]) if h["rates"][i] is not None), 0.0)
        y0 = logit(r)
        b, res, n = fits[i]
        slope = SHRINK * b + (1 - SHRINK) * pooled.get(t["tier"], 0.0) if n >= 2 else 0.0
        move = max(-MAX_MOVE, min(MAX_MOVE, DAMP * slope * dx))
        if r >= 99.9:
            move = min(move, 0.0)
        mu = y0 + move
        count = clamp(r) / 100 * players
        noise = 1 / math.sqrt(max(count, 1.0)) if players else 0.3
        sigma = math.sqrt(0.22 ** 2 + (0.7 * move) ** 2 + min(res, 1.0) ** 2 + min(noise, 1.0) ** 2 * 0.5)
        if r >= 99.9 or r <= 0.01:
            sigma = max(sigma, 0.8)
        q = [round4(min(100.0, max(0.0, inv(mu + z * sigma)))) for z in Z]
        for k in range(1, 5):
            if q[k] < q[k - 1]:
                q[k] = q[k - 1]
        rows.append({"id": t["id"], "q": q})
    return {"trophies": rows}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        out = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
