"""Score the judge against the labels.

    python -m eval.metrics [--labels gold_draft.json]

Every number comes with a stratified bootstrap 95% interval, because a 55-thread sample with six
positives can produce an accuracy that looks excellent and means very little. Where the interval
is wide, the report says so rather than quoting the point estimate alone.

Two populations are reported separately and never mixed into one headline:
  inbox    the recent inbox as it actually arrives — this is operational performance
  replied  threads the person did in fact answer, added on purpose to have positives at all
Mixing them would inflate the positive rate above what a real mailbox has.

No third-party packages; the primitives are the same ones used in the contest-radar evaluation.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path

from replydesk.questions import email as qs

DATA = Path(__file__).resolve().parent / "data"
BOOT = 2000
SEED = 7
EPS = 1e-6


# ---------- primitives (w = per-item weight) ----------

def confusion(y, p, w):
    tp = sum(wi for yi, pi, wi in zip(y, p, w) if yi and pi)
    fp = sum(wi for yi, pi, wi in zip(y, p, w) if not yi and pi)
    fn = sum(wi for yi, pi, wi in zip(y, p, w) if yi and not pi)
    tn = sum(wi for yi, pi, wi in zip(y, p, w) if not yi and not pi)
    return tp, fp, fn, tn


def cls_metrics(y, p, w):
    tp, fp, fn, tn = confusion(y, p, w)
    n = tp + fp + fn + tn
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else 0.0
    den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return {"accuracy": (tp + tn) / n if n else None, "precision": prec, "recall": rec,
            "f1": f1, "mcc": (tp * tn - fp * fn) / den if den else 0.0,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def auroc(y, s, w):
    """Weighted Mann-Whitney AUC (ties count half)."""
    pos = [(si, wi) for yi, si, wi in zip(y, s, w) if yi]
    neg = [(si, wi) for yi, si, wi in zip(y, s, w) if not yi]
    if not pos or not neg:
        return None
    num = sum(wp * wn * (1.0 if sp > sn else 0.5 if sp == sn else 0.0)
              for sp, wp in pos for sn, wn in neg)
    return num / (sum(w for _, w in pos) * sum(w for _, w in neg))


def avg_precision(y, s, w):
    order = sorted(zip(s, y, w), key=lambda t: -t[0])
    total_pos = sum(wi for _, yi, wi in order if yi)
    if not total_pos:
        return None
    tp = fp = ap = 0.0
    for _, yi, wi in order:
        if yi:
            tp += wi
            ap += wi / total_pos * (tp / (tp + fp))
        else:
            fp += wi
    return ap


def brier(y, s, w):
    return sum(wi * (si - yi) ** 2 for yi, si, wi in zip(y, s, w)) / sum(w)


def log_loss(y, s, w):
    return -sum(wi * (math.log(max(si, EPS)) if yi else math.log(max(1 - si, EPS)))
                for yi, si, wi in zip(y, s, w)) / sum(w)


def reliability(y, s, w, bins=10):
    rows = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, si in enumerate(s) if lo <= si < hi or (b == bins - 1 and si == 1.0)]
        if not idx:
            continue
        wt = sum(w[i] for i in idx)
        rows.append({"lo": lo, "hi": hi, "n": len(idx), "weight": wt,
                     "meanPred": sum(w[i] * s[i] for i in idx) / wt,
                     "fracPos": sum(w[i] * y[i] for i in idx) / wt})
    return rows


def ece(y, s, w, bins=10):
    rows = reliability(y, s, w, bins)
    total = sum(w)
    return sum(r["weight"] / total * abs(r["meanPred"] - r["fracPos"]) for r in rows)


def cohen_kappa(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if not pairs:
        return None
    n = len(pairs)
    po = sum(x == y for x, y in pairs) / n
    ca, cb = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    pe = sum(ca[k] * cb[k] for k in ca) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def mcnemar_exact(b, c):
    """Two-sided exact binomial test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def macro_f1(y, p, labels):
    f1s = []
    for c in labels:
        tp = sum(1 for a, b in zip(y, p) if a == c and b == c)
        fp = sum(1 for a, b in zip(y, p) if a != c and b == c)
        fn = sum(1 for a, b in zip(y, p) if a == c and b != c)
        if tp + fp + fn:
            f1s.append(2 * tp / (2 * tp + fp + fn))
    return sum(f1s) / len(f1s) if f1s else None


def spearman(a, b):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            mean = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = mean
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else None


# ---------- bootstrap ----------

def bootstrap(rows, fn, seed=SEED):
    """95% percentile interval, resampling inside each stratum."""
    rng = random.Random(seed)
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["stratum"], []).append(r)
    vals = []
    for _ in range(BOOT):
        res = [rng.choice(g) for g in groups.values() for _ in g]
        v = fn(res)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            vals.append(v)
    if len(vals) < BOOT // 2:
        return None
    vals.sort()
    return [round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4)]


def with_ci(rows, fn):
    v = fn(rows)
    return {"value": round(v, 4) if isinstance(v, float) else v, "ci95": bootstrap(rows, fn)}


# ---------- loading ----------

def load(labels_file: str) -> tuple[list[dict], dict]:
    labels = {r["key"]: r for r in json.loads((DATA / labels_file).read_text(encoding="utf-8"))}
    # Whatever the reviewer has confirmed so far wins over the draft, row by row: the measurement
    # stays runnable mid-review instead of waiting for all 55.
    gold_file = DATA / "gold.json"
    if gold_file.exists():
        for key, gold in json.loads(gold_file.read_text(encoding="utf-8")).items():
            if key in labels:
                labels[key]["gold"] = gold
    runs: dict[str, dict[int, dict]] = {}
    for line in (DATA / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            runs.setdefault(row["key"], {})[row["run"]] = row
    threads = {}
    for path in sorted((DATA / "threads").glob("*.json")):
        t = json.loads(path.read_text(encoding="utf-8"))
        threads[t["key"]] = t

    rows = []
    for key, label in labels.items():
        if key not in runs or 0 not in runs[key]:
            continue
        answers = runs[key][0]["answers"]
        gold = label.get("gold") or label["draft"]       # 검수본이 있으면 그것이 정답
        rows.append({
            "key": key, "n": label["n"], "subject": label["subject"],
            "account": label["key"].split(":")[0],
            "stratum": "replied" if label["replied_later"] else "inbox",
            "replied_later": label["replied_later"],
            "gold": gold, "draft": label["draft"],
            "reviewed": "gold" in label,
            "answers": answers,
            "repeats": [runs[key][r]["answers"] for r in sorted(runs[key])],
            "seconds": runs[key][0]["seconds"], "usage": runs[key][0]["usage"],
            "text": " ".join((threads[key]["subject"] + " " +
                              threads[key]["messages"][-1]["text"]).split())[:1500],
            "sender": threads[key]["messages"][-1]["sender"],
        })
    return rows, threads


# ---------- the judged questions ----------

def binary(rows, question: str, threshold: float) -> dict:
    keep = [r for r in rows if r["gold"].get(question) is not None]
    if not keep:
        return {"n": 0}
    y = [bool(r["gold"][question]) for r in keep]
    s = [float(r["answers"].get(question, {}).get("value", 0.0)) for r in keep]
    w = [1.0] * len(keep)
    out = {"n": len(keep), "positives": sum(y), "threshold": threshold}
    out.update({k: round(v, 4) if isinstance(v, float) else v
                for k, v in cls_metrics(y, [si >= threshold for si in s], w).items()})
    for name, fn in (("auroc", auroc), ("ap", avg_precision)):
        out[name] = with_ci(keep, lambda rs, f=fn, q=question, t=threshold: f(
            [bool(r["gold"][q]) for r in rs],
            [float(r["answers"].get(q, {}).get("value", 0.0)) for r in rs],
            [1.0] * len(rs)))
    out["accuracyCi"] = bootstrap(keep, lambda rs, q=question, t=threshold: cls_metrics(
        [bool(r["gold"][q]) for r in rs],
        [float(r["answers"].get(q, {}).get("value", 0.0)) >= t for r in rs],
        [1.0] * len(rs))["accuracy"])
    out["brier"] = round(brier(y, s, w), 4)
    out["logLoss"] = round(log_loss(y, s, w), 4)
    out["ece"] = round(ece(y, s, w), 4)
    out["reliability"] = reliability(y, s, w)
    out["errors"] = [{"n": r["n"], "subject": r["subject"][:60],
                      "gold": r["gold"][question], "p": round(
                          float(r["answers"].get(question, {}).get("value", 0.0)), 3)}
                     for r in keep
                     if bool(r["gold"][question]) != (
                         float(r["answers"].get(question, {}).get("value", 0.0)) >= threshold)]
    return out


def urgency_metrics(rows) -> dict:
    keep = [r for r in rows if r["gold"].get("urgency") is not None]
    gold = [float(r["gold"]["urgency"]) for r in keep]
    pred = [float(r["answers"].get("urgency", {}).get("value", 0.0)) for r in keep]
    diffs = [abs(g - p) for g, p in zip(gold, pred)]
    return {
        "n": len(keep),
        "mae": round(sum(diffs) / len(diffs), 3),
        "within1": round(sum(d <= 1 for d in diffs) / len(diffs), 4),
        "exact": round(sum(round(p) == g for g, p in zip(gold, pred)) / len(keep), 4),
        "spearman": round(spearman(gold, pred), 4),
        "maeCi": bootstrap(keep, lambda rs: sum(
            abs(float(r["gold"]["urgency"]) - float(r["answers"].get("urgency", {}).get("value", 0.0)))
            for r in rs) / len(rs)),
        "byGold": {int(g): round(sum(p for gg, p in zip(gold, pred) if gg == g) /
                                 max(1, sum(gg == g for gg in gold)), 2)
                   for g in sorted(set(gold))},
    }


def sweep(rows, question: str) -> dict:
    """Accuracy across every threshold, because the default 0.5 is an assumption, not a result.

    The best row here is optimistic — it is chosen on the same 55 threads it is scored on. It is
    reported as "where the cut should probably move", never as the system's accuracy.
    """
    keep = [r for r in rows if r["gold"].get(question) is not None]
    y = [bool(r["gold"][question]) for r in keep]
    s = [float(r["answers"].get(question, {}).get("value", 0.0)) for r in keep]
    out = []
    for t in [i / 20 for i in range(1, 20)]:
        m = cls_metrics(y, [si >= t for si in s], [1.0] * len(y))
        out.append({"threshold": round(t, 2), "accuracy": round(m["accuracy"], 4),
                    "f1": round(m["f1"], 4), "fp": m["fp"], "fn": m["fn"]})
    best = max(out, key=lambda r: (r["accuracy"], -r["fn"]))
    return {"curve": out, "best": best, "current": next(
        r for r in out if abs(r["threshold"] - qs.THRESHOLDS[question]) < 1e-9)}


def conditional_elsewhere(rows) -> dict:
    """`action_elsewhere` only ever decides anything after `needs_reply` has passed.

    Scored over the whole mailbox it looks near-random, but production never asks it about a
    newsletter. The number that matters is the one measured where it is actually consulted.
    """
    keep = [r for r in rows if r["gold"].get("needs_reply") and
            r["gold"].get("action_elsewhere") is not None]
    if len(keep) < 3:
        return {"n": len(keep), "note": "조건을 만족하는 건수가 너무 적어 수치를 내지 않습니다"}
    y = [bool(r["gold"]["action_elsewhere"]) for r in keep]
    p = [float(r["answers"].get("action_elsewhere", {}).get("value", 0.0)) >=
         qs.THRESHOLDS["action_elsewhere"] for r in keep]
    m = {k: round(v, 4) if isinstance(v, float) else v
         for k, v in cls_metrics(y, p, [1.0] * len(y)).items()}
    m["n"] = len(keep)
    m["rows"] = [{"n": r["n"], "subject": r["subject"][:50], "gold": r["gold"]["action_elsewhere"],
                  "p": round(float(r["answers"].get("action_elsewhere", {}).get("value", 0.0)), 3)}
                 for r in keep]
    return m


def gold_route(gold: dict) -> str:
    """The same branching as production, run on the human labels instead of the model's."""
    if not gold.get("needs_reply"):
        return "skip"
    if gold.get("action_elsewhere"):
        return "elsewhere"
    if gold.get("needs_human"):
        return "human"
    return "draft"


def routing(rows) -> dict:
    keep = [r for r in rows if r["gold"].get("needs_reply") is not None]
    g = [gold_route(r["gold"]) for r in keep]
    p = [qs.route(r["answers"]) for r in keep]
    labels = ["skip", "elsewhere", "human", "draft"]
    matrix = {a: {b: sum(1 for x, y in zip(g, p) if x == a and y == b) for b in labels}
              for a in labels}
    # The expensive mistake is not a mislabel, it is silence: mail that needed an answer and was
    # dropped. Counted on its own because one of these costs more than ten wasted drafts.
    missed = [{"n": r["n"], "subject": r["subject"][:60]}
              for r, gi, pi in zip(keep, g, p) if gi != "skip" and pi == "skip"]
    return {
        "n": len(keep),
        "accuracy": round(sum(x == y for x, y in zip(g, p)) / len(keep), 4),
        "accuracyCi": bootstrap(keep, lambda rs: sum(
            gold_route(r["gold"]) == qs.route(r["answers"]) for r in rs) / len(rs)),
        "macroF1": round(macro_f1(g, p, labels), 4),
        "matrix": matrix,
        "missed": missed,
        "actedWhenSkip": sum(1 for x, y in zip(g, p) if x == "skip" and y != "skip"),
    }


def baseline(rows) -> dict:
    """A keyword rule, to show what the judge is actually worth over the obvious thing.

    The rule people write first: a reply is needed if the mail is not machine-sent and asks
    something. It is the honest comparison — not a straw man, just shallow.
    """
    import re
    auto = re.compile(r"no-?reply|발신전용|noreply|automated|unsubscribe|수신거부", re.I)
    asks = re.compile(r"\?|회신|답장|알려\s?주|부탁드립니다|reply|respond|let me know", re.I)
    keep = [r for r in rows if r["gold"].get("needs_reply") is not None]
    y = [bool(r["gold"]["needs_reply"]) for r in keep]
    p = [bool(asks.search(r["text"])) and not auto.search(r["text"]) for r in keep]
    judged = [float(r["answers"].get("needs_reply", {}).get("value", 0.0)) >=
              qs.THRESHOLDS["needs_reply"] for r in keep]
    b = sum(1 for yi, ji, pi in zip(y, judged, p) if ji == yi and pi != yi)   # judge right only
    c = sum(1 for yi, ji, pi in zip(y, judged, p) if ji != yi and pi == yi)   # rule right only
    out = {k: round(v, 4) if isinstance(v, float) else v for k, v in cls_metrics(y, p, [1.0] * len(y)).items()}
    out.update({"n": len(keep), "judgeOnlyRight": b, "ruleOnlyRight": c,
                "mcnemarP": round(mcnemar_exact(b, c), 5)})
    return out


def consistency(rows) -> dict:
    """Ask the same mail the same questions three times: how far do the answers move?"""
    out = {}
    for q in ("needs_reply", "action_elsewhere", "needs_human"):
        spreads, flips = [], 0
        for r in rows:
            vals = [float(a.get(q, {}).get("value", 0.0)) for a in r["repeats"]]
            if len(vals) < 2:
                continue
            spreads.append(max(vals) - min(vals))
            decisions = {v >= qs.THRESHOLDS.get(q, 0.5) for v in vals}
            flips += len(decisions) > 1
        if spreads:
            out[q] = {"runs": len(rows[0]["repeats"]), "meanSpread": round(sum(spreads) / len(spreads), 4),
                      "maxSpread": round(max(spreads), 4), "decisionFlips": flips, "n": len(spreads)}
    urg = [[float(a.get("urgency", {}).get("value", 0.0)) for a in r["repeats"]] for r in rows]
    urg = [v for v in urg if len(v) > 1]
    if urg:
        out["urgency"] = {"meanSpread": round(sum(max(v) - min(v) for v in urg) / len(urg), 4),
                          "maxSpread": round(max(max(v) - min(v) for v in urg), 4)}
    return out


def selective(rows, question="needs_reply") -> list[dict]:
    """If we only act where the judge is confident, how much better is it — and at what cost?"""
    keep = [r for r in rows if r["gold"].get(question) is not None]
    scored = sorted(keep, key=lambda r: -abs(
        float(r["answers"].get(question, {}).get("value", 0.5)) - 0.5))
    out = []
    for cov in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        part = scored[:max(1, round(cov * len(scored)))]
        y = [bool(r["gold"][question]) for r in part]
        p = [float(r["answers"].get(question, {}).get("value", 0.0)) >=
             qs.THRESHOLDS[question] for r in part]
        out.append({"coverage": cov, "n": len(part),
                    "accuracy": round(sum(a == b for a, b in zip(y, p)) / len(part), 4)})
    return out


def behavioural(rows) -> dict:
    """The threads the person actually answered — what did the judge say about those?"""
    keep = [r for r in rows if r["replied_later"]]
    if not keep:
        return {"n": 0}
    hits = [r for r in keep
            if float(r["answers"].get("needs_reply", {}).get("value", 0.0)) >=
            qs.THRESHOLDS["needs_reply"]]
    return {"n": len(keep), "flaggedNeedsReply": len(hits),
            "recall": round(len(hits) / len(keep), 4),
            "missed": [{"n": r["n"], "subject": r["subject"][:60],
                        "p": round(float(r["answers"].get("needs_reply", {}).get("value", 0.0)), 3)}
                       for r in keep if r not in hits]}


def label_agreement(rows) -> dict:
    """Claude's blind draft vs the person's review — reported, not hidden."""
    reviewed = [r for r in rows if r["reviewed"]]
    if not reviewed:
        return {"reviewed": 0, "note": "아직 검수 전 — 아래 수치의 정답은 Claude 초안입니다"}
    out = {"reviewed": len(reviewed)}
    for q in ("needs_reply", "action_elsewhere", "needs_human"):
        a = [r["draft"].get(q) for r in reviewed]
        b = [r["gold"].get(q) for r in reviewed]
        pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
        out[q] = {"agree": sum(x == y for x, y in pairs), "n": len(pairs),
                  "kappa": round(cohen_kappa(a, b), 4) if cohen_kappa(a, b) is not None else None}
    return out


def run(rows) -> dict:
    return {
        "needs_reply": binary(rows, "needs_reply", qs.THRESHOLDS["needs_reply"]),
        "action_elsewhere": binary(rows, "action_elsewhere", qs.THRESHOLDS["action_elsewhere"]),
        "needs_human": binary(rows, "needs_human", qs.THRESHOLDS["needs_human"]),
        "urgency": urgency_metrics(rows),
        "routing": routing(rows),
        "thresholdSweep": {q: sweep(rows, q) for q in ("needs_reply", "action_elsewhere")},
        "elsewhereWhenConsulted": conditional_elsewhere(rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="판단 정확도 지표 계산")
    ap.add_argument("--labels", default="gold_draft.json")
    args = ap.parse_args()

    rows, _ = load(args.labels)
    inbox = [r for r in rows if r["stratum"] == "inbox"]
    seconds = sorted(r["seconds"] for r in rows)
    tokens = [r["usage"].get("inputTokens") or r["usage"].get("input_tokens") or 0 for r in rows]

    result = {
        "sample": {"threads": len(rows),
                   "byStratum": dict(Counter(r["stratum"] for r in rows)),
                   "byAccount": dict(Counter(r["account"] for r in rows)),
                   "reviewed": sum(r["reviewed"] for r in rows),
                   "labels": args.labels},
        "cost": {"medianSeconds": round(seconds[len(seconds) // 2], 3),
                 "p95Seconds": round(seconds[int(0.95 * len(seconds)) - 1], 3),
                 "meanInputTokens": round(sum(tokens) / len(tokens)),
                 "usdPerThread": round(sum(tokens) / len(tokens) / 1e6 * 0.042, 6),
                 "usdPerThousand": round(sum(tokens) / len(tokens) / 1e6 * 0.042 * 1000, 3)},
        "all": run(rows),
        "inboxOnly": run(inbox),
        "baseline": baseline(rows),
        "consistency": consistency(rows),
        "selective": selective(rows),
        "behavioural": behavioural(rows),
        "labelAgreement": label_agreement(rows),
    }
    out = DATA / "results.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    a = result["all"]
    print(f"표본 {len(rows)}건 (받은편지함 {len(inbox)} · 실제 답장 {len(rows) - len(inbox)})"
          f" · 검수 {result['sample']['reviewed']}건")
    print(f"건당 {result['cost']['medianSeconds']}초 · ${result['cost']['usdPerThread']:.6f}")
    for q in ("needs_reply", "action_elsewhere", "needs_human"):
        m = a[q]
        ci = m["auroc"]["ci95"]
        print(f"{q:17} 정확도 {m['accuracy']:.3f} · AUROC {m['auroc']['value']} "
              f"[{ci[0]}, {ci[1]}] · ECE {m['ece']:.3f} · 양성 {m['positives']}/{m['n']} "
              f"· 틀림 {len(m['errors'])}건" if ci else f"{q}: {m}")
    u = a["urgency"]
    print(f"{'urgency':17} MAE {u['mae']} · ±1 안 {u['within1']:.2f} · 순위상관 {u['spearman']}")
    r = a["routing"]
    print(f"{'routing':17} 정확도 {r['accuracy']:.3f} {r['accuracyCi']} · 놓친 답장 {len(r['missed'])}건")
    print(f"규칙 기반 대조군 정확도 {result['baseline']['accuracy']:.3f} "
          f"· McNemar p={result['baseline']['mcnemarP']}")
    sw = a["thresholdSweep"]["needs_reply"]
    print(f"{'임계값':17} 현재 {sw['current']['threshold']} → 정확도 {sw['current']['accuracy']:.3f}"
          f" (헛초안 {sw['current']['fp']}, 놓침 {sw['current']['fn']}) · "
          f"표본상 최적 {sw['best']['threshold']} → {sw['best']['accuracy']:.3f}"
          f" (헛초안 {sw['best']['fp']}, 놓침 {sw['best']['fn']})")
    ce = a["elsewhereWhenConsulted"]
    print(f"{'폼·링크 판단':15} 실제로 쓰이는 조건에서만: n={ce['n']}"
          + (f" · 정확도 {ce['accuracy']:.3f}" if ce.get("accuracy") is not None else f" — {ce.get('note','')}"))
    print(f"→ {out}")


if __name__ == "__main__":
    main()
