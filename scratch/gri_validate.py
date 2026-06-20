#!/usr/bin/env python
"""Grounding experiment: does concept(column)-driven retrieval recover GRI golden measurable positions?
Reuses smartmap's embedding + vector machinery. Measures recall@N vs disclosure-9 golden."""
import sys, os, json, re, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import smartmap as sm

class A:
    data = out = framework = None; template = 24; disclosure = 9
    conf = 0.55; floor = 0.50
    no_judge = no_judge_cache = refresh_data = refresh_embeddings = False; ssh_host = "sofi"
cfg = sm.Cfg(A()); cfg.fw_code = "GRI"

def en(x): return x.get("en", "") if isinstance(x, dict) else str(x or "")
doc = json.load(open(cfg.tmpl_file(), encoding="utf-8"))

# grid questions -> concepts (title + all column descriptions)
grid = {}
def walk(n):
    if isinstance(n, dict):
        if n.get("nodeType") == "question" and n.get("displayType") == "grid":
            cols = [en(c.get("description")) for c in (n.get("columns") or []) if isinstance(c, dict)]
            cols = [re.sub(r"\s+", " ", c).strip() for c in cols if c and c.strip()]
            grid[n.get("nodeId")] = {"title": en(n.get("title")), "concepts": cols}
        for v in n.values(): walk(v)
    elif isinstance(n, list):
        for v in n: walk(v)
walk(doc)

sid2qid = {}
for line in open(cfg.p("disc9_sid2qid.tsv")):
    f = line.strip().split("\t")
    if len(f) == 2: sid2qid[f[0]] = f[1]
golden = collections.defaultdict(set); gtype = {}
for line in open(cfg.p("disc9_golden.tsv")):
    f = line.strip().split("\t")
    if len(f) >= 3: golden[f[0]].add(int(f[1])); gtype[int(f[1])] = f[2]
MEAS = {"Flow", "Indicator", "Asset"}

pos = sm.load_positions(cfg)
posv = sm.position_vectors(cfg, pos); pn = {k: sm._norm(v) for k, v in posv.items()}; pids = list(pn)
allc = sorted({c for g in grid.values() for c in g["concepts"]})
cv = sm.concept_vectors(cfg, allc); cn = {k: sm._norm(v) for k, v in cv.items()}
print(f"[validate] {len(grid)} grid questions, {len(allc)} unique column-concepts, {len(pids)} positions")

parent_path = lambda pid: "/".join([x for x in pos["path"].get(pid, "").split("/") if x][:-1])
sibs = collections.defaultdict(set)
for p in pos["path"]: sibs[parent_path(p)].add(p)
def topk(vec, k): return sorted(((p, sm._dot(vec, pn[p])) for p in pids), key=lambda x: -x[1])[:k]

NS = [10, 20, 30, 50]
agg = {n: [] for n in NS}; seed = {n: 0 for n in NS}; nq = 0
for nid, g in grid.items():
    dqid = sid2qid.get(nid)
    gold_meas = {p for p in golden.get(dqid, set()) if gtype.get(p) in MEAS}
    if not gold_meas: continue
    nq += 1
    cand = {}
    for c in g["concepts"]:
        if c not in cn: continue
        for p, s in topk(cn[c], 3):
            cand[p] = max(cand.get(p, 0), s)
            for sp in sibs.get(parent_path(p), {p}):
                cand.setdefault(sp, sm._dot(cn[c], pn[sp]))
    ranked = [p for p, _ in sorted(cand.items(), key=lambda x: -x[1])]
    for n in NS:
        got = gold_meas & set(ranked[:n])
        agg[n].append(len(got) / len(gold_meas))
        if got: seed[n] += 1
print(f"[validate] evaluated {nq} questions with measurable golden\n")
print(f"{'N':>4} | {'mean recall':>11} | {'seed-rate (≥1 hit)':>18}")
for n in NS:
    mr = sum(agg[n]) / len(agg[n]) if agg[n] else 0
    print(f"{n:>4} | {mr:>10.1%} | {seed[n]}/{nq} = {seed[n]/nq:>6.1%}")
