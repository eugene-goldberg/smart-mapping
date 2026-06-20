#!/usr/bin/env python
"""Lever-exploration harness for GRI quantitative mapping. Embeds ONCE (disk-cached),
then sweeps selection recipes + scoring definitions to beat the 60.5% F1 baseline.

Levers: reference set (grid-only vs all-golden questions), transfer-K, shortlist size,
adaptive cut (rel-floor / score-gap), consensus weighting (sum/count/sum*count),
fusion with concept retrieval, sibling expansion. Scoring: exact-ID and near-match
(granularity-tolerant: exact/parent/child/sibling)."""
import sys, os, json, re, collections, pickle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import esrsmap as sm

class A:
    data = out = framework = None; template = 24; disclosure = 9; conf = .55; floor = .5
    no_judge = no_judge_cache = refresh_data = refresh_embeddings = False; ssh_host = "sofi"
cfg = sm.Cfg(A()); cfg.fw_code = "GRI"
MEAS = {"Flow", "Indicator", "Asset"}
def en(x): return x.get("en", "") if isinstance(x, dict) else str(x or "")
def clean(s): return re.sub(r"\s+", " ", s or "").strip()

# ---- load template: ALL question nodes (text) + which are grid ----
doc = json.load(open(cfg.tmpl_file(), encoding="utf-8"))
qnode = {}   # nodeId -> {qtext, grid, concepts}
def walk(n):
    if isinstance(n, dict):
        if n.get("nodeType") == "question":
            grid = n.get("displayType") == "grid"
            cols = [clean(en(c.get("description"))) for c in (n.get("columns") or []) if isinstance(c, dict)] if grid else []
            qnode[n.get("nodeId")] = {"qtext": (clean(en(n.get("title"))) + ". " + clean(en(n.get("description"))))[:2000],
                                      "grid": grid, "concepts": [c for c in cols if c]}
        for v in n.values(): walk(v)
    elif isinstance(n, list):
        for v in n: walk(v)
walk(doc)
sid2qid = {}
for l in open(cfg.p("disc9_sid2qid.tsv")):
    f = l.strip().split("\t");  sid2qid.update({f[0]: f[1]}) if len(f) == 2 else None
golden = collections.defaultdict(set); gtype = {}
for l in open(cfg.p("disc9_golden.tsv")):
    f = l.strip().split("\t")
    if len(f) >= 3: golden[f[0]].add(int(f[1])); gtype[int(f[1])] = f[2]
gmeas = lambda nid: {p for p in golden.get(sid2qid.get(nid), set()) if gtype.get(p) in MEAS}

pos = sm.load_positions(cfg)

# ---- disk-cached embeddings ----
CACHE = cfg.p("gri_emb_cache.pkl")
cache = pickle.load(open(CACHE, "rb")) if os.path.exists(CACHE) else {}
def embed_cached(texts):
    miss = [t for t in {t for t in texts if t} if t not in cache]
    if miss:
        for t, v in zip(miss, sm._embed(cfg, miss)): cache[t] = v
        pickle.dump(cache, open(CACHE, "wb"))
    return {t: sm._norm(cache[t]) for t in texts if t in cache}

def rich(pid):
    segs = [int(x) for x in pos["path"].get(pid, "").split("/") if x]
    lin = " > ".join(pos["name"].get(s, "") for s in segs[:-1] if pos["name"].get(s, ""))
    parts = [pos["name"].get(pid, "")]
    if pos["desc"].get(pid): parts.append(pos["desc"][pid].strip())
    if lin: parts.append("Category: " + lin)
    if pos["unit"].get(pid): parts.append("Unit: " + pos["unit"][pid])
    if pos["type"].get(pid): parts.append("Type: " + pos["type"][pid])
    return re.sub(r"\s+", " ", " . ".join(parts)).strip()

pids = [p for p in pos["name"] if p in pos["path"]]
print(f"[embed] positions={len(pids)} (cache has {len(cache)})")
pn = embed_cached([rich(p) for p in pids]); pn = {p: pn[rich(p)] for p in pids if rich(p) in pn}
qtexts = {nid: q["qtext"] for nid, q in qnode.items() if q["qtext"]}
qe = embed_cached(list(qtexts.values())); qn = {nid: qe[t] for nid, t in qtexts.items() if t in qe}
concs = sorted({c for q in qnode.values() for c in q["concepts"]})
ce = embed_cached(concs); cn = {c: ce[c] for c in concs if c in ce}
print(f"[embed] done. cache now {len(cache)}")

# ---- tree helpers ----
parent = {};
for p in pids:
    segs = [int(x) for x in pos["path"][p].split("/") if x]
    parent[p] = segs[-2] if len(segs) >= 2 else 0
sibs = collections.defaultdict(set)
for p in pids: sibs[parent[p]].add(p)
def near(pred, gold):
    if pred == gold: return True
    return parent.get(pred) == gold or parent.get(gold) == pred or (parent.get(pred) and parent.get(pred) == parent.get(gold))
def topk_pos(vec, k): return sorted(((p, sm._dot(vec, pn[p])) for p in pids if p in pn), key=lambda x: -x[1])[:k]

# ---- targets + reference universe ----
TARGETS = [nid for nid, q in qnode.items() if q["grid"] and gmeas(nid)]          # grid questions w/ measurable golden
REF_GRID = set(TARGETS)
REF_ALL = {nid for nid in qnode if gmeas(nid) and nid in qn}                      # any golden question w/ measurable
print(f"[data] targets(grid)={len(TARGETS)}  ref_grid={len(REF_GRID)}  ref_all={len(REF_ALL)}\n")

def neighbors(nid, refset, K):
    return sorted(((o, sm._dot(qn[nid], qn[o])) for o in refset if o != nid and o in qn),
                  key=lambda x: -x[1])[:K]

def consensus(nid, refset, K, weight):
    sc = collections.defaultdict(float)
    for o, s in neighbors(nid, refset, K):
        for p in gmeas(o):
            if p in pn:
                if weight == "sum": sc[p] += s
                elif weight == "count": sc[p] += 1
                elif weight == "sumcount": sc[p] += s  # base; count handled below
    if weight == "sumcount":
        cnt = collections.defaultdict(int)
        for o, s in neighbors(nid, refset, K):
            for p in gmeas(o):
                if p in pn: cnt[p] += 1
        sc = {p: v * cnt[p] for p, v in sc.items()}
    return sorted(sc.items(), key=lambda x: -x[1])

def select(ranked, N, rel, gap, expand):
    if not ranked: return []
    top = ranked[0][1]
    out = [(p, s) for p, s in ranked[:N] if s >= rel * top]
    if gap:  # cut at first big relative drop
        cut = []
        for i, (p, s) in enumerate(out):
            if i and s < gap * out[i-1][1]: break
            cut.append((p, s))
        out = cut
    if expand:  # add siblings of selected (cheap recall boost)
        sel = {p for p, _ in out}
        for p, _ in list(out):
            for sp in sibs.get(parent.get(p), set()):
                if sp not in sel: out.append((sp, 0.0)); sel.add(sp)
    return out

def fuse(nid, refset, K, wt, alpha):
    base = dict(consensus(nid, refset, K, wt))
    if alpha > 0:  # add concept similarity
        for c in qnode[nid]["concepts"]:
            if c in cn:
                for p, s in topk_pos(cn[c], 3): base[p] = max(base.get(p, 0), alpha * s)
    return sorted(base.items(), key=lambda x: -x[1])

def evaluate(name, rankfn, N=8, rel=0.5, gap=0.0, expand=False):
    ex_r = ex_p = nr_r = nr_p = 0; n = 0
    for nid in TARGETS:
        gold = gmeas(nid)
        if not gold: continue
        n += 1
        sel = [p for p, _ in select(rankfn(nid), N, rel, gap, expand)]
        if not sel: continue
        exr = len(gold & set(sel)) / len(gold); exp = len(gold & set(sel)) / len(sel)
        nrh_g = sum(1 for g in gold if any(near(p, g) for p in sel)) / len(gold)
        nrh_p = sum(1 for p in sel if any(near(p, g) for g in gold)) / len(sel)
        ex_r += exr; ex_p += exp; nr_r += nrh_g; nr_p += nrh_p
    f1 = lambda r, p: 2*r*p/(r+p) if r+p else 0
    er, ep, nrr, nrp = ex_r/n, ex_p/n, nr_r/n, nr_p/n
    print(f"  {name:46} exact R={er:.0%} P={ep:.0%} F1={f1(er,ep):.0%}  |  near R={nrr:.0%} P={nrp:.0%} F1={f1(nrr,nrp):.0%}")
    return f1(er, ep)

print("BASELINE (shipped: grid-ref, K=5, N=8, rel=0.5, sum)")
evaluate("baseline", lambda nid: consensus(nid, REF_GRID, 5, "sum"), N=8, rel=0.5)
print("\nLEVER 1 — reference universe (all golden questions, not just grid)")
for K in (5, 8, 12):
    evaluate(f"ref=ALL K={K} N=8 sum", lambda nid, K=K: consensus(nid, REF_ALL, K, "sum"), N=8, rel=0.5)
print("\nLEVER 2 — consensus weighting (ref=ALL, K=8, N=8)")
for wt in ("sum", "count", "sumcount"):
    evaluate(f"weight={wt}", lambda nid, wt=wt: consensus(nid, REF_ALL, 8, wt), N=8, rel=0.5)
print("\nLEVER 3 — shortlist size & relative floor (ref=ALL, K=8, sum)")
for N in (5, 8, 12, 20):
    for rel in (0.3, 0.5, 0.7):
        evaluate(f"N={N} rel={rel}", lambda nid: consensus(nid, REF_ALL, 8, "sum"), N=N, rel=rel)
print("\nLEVER 4 — score-gap adaptive cut (ref=ALL, K=8, N=20)")
for gap in (0.5, 0.65, 0.8):
    evaluate(f"gap={gap}", lambda nid: consensus(nid, REF_ALL, 8, "sum"), N=20, rel=0.0, gap=gap)
print("\nLEVER 5 — sibling expansion (ref=ALL, K=8, N=8)")
evaluate("expand=on", lambda nid: consensus(nid, REF_ALL, 8, "sum"), N=8, rel=0.5, expand=True)
print("\nLEVER 6 — fusion with concept retrieval (ref=ALL, K=8, N=8)")
for a in (0.3, 0.6, 1.0):
    evaluate(f"alpha={a}", lambda nid, a=a: fuse(nid, REF_ALL, 8, "sum", a), N=8, rel=0.5)

# LEVER 7 — localize-then-specialize: consensus picks the subtree(s); columns pick exact leaves
def localize_specialize(nid, K, P_parents):
    cons = consensus(nid, REF_ALL, K, "sum")
    if not cons: return []
    pscore = collections.defaultdict(float)
    for p, s in cons: pscore[parent.get(p)] += s
    top_parents = {pa for pa, _ in sorted(pscore.items(), key=lambda x: -x[1])[:P_parents]}
    cand = [p for p in pids if parent.get(p) in top_parents]
    sc = {}
    for c in qnode[nid]["concepts"]:
        if c in cn:
            for p in cand: sc[p] = max(sc.get(p, 0), sm._dot(cn[c], pn[p]))
    if not sc:  # no column concepts -> fall back to consensus order within the subtree
        sc = {p: s for p, s in cons if p in set(cand)}
    return sorted(sc.items(), key=lambda x: -x[1])
print("\nLEVER 7 — localize (consensus subtree) then specialize (column match)")
for P in (2, 3, 4):
    for N in (8, 12):
        evaluate(f"parents={P} N={N}", lambda nid, P=P: localize_specialize(nid, 8, P), N=N, rel=0.4)

# LEVER 8 — hybrid: consensus shortlist UNION localize-specialize leaves (recall of both)
def hybrid(nid):
    a = dict(consensus(nid, REF_ALL, 8, "sum"))
    amax = max(a.values()) if a else 1.0
    b = localize_specialize(nid, 8, 3)
    out = {p: s / amax for p, s in a.items()}
    bmax = max((s for _, s in b), default=1.0) or 1.0
    for p, s in b: out[p] = max(out.get(p, 0), s / bmax)
    return sorted(out.items(), key=lambda x: -x[1])
print("\nLEVER 8 — hybrid consensus ∪ localize-specialize (normalized)")
for N in (8, 12):
    for rel in (0.4, 0.5):
        evaluate(f"hybrid N={N} rel={rel}", hybrid, N=N, rel=rel)
