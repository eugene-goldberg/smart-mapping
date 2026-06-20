#!/usr/bin/env python
"""Recipe sweep (single embedding pass) to find a GRI retrieval method that recovers golden.
Recipes: R1 columns-only; R2 +question text; R3 wider topk; R4 full subtree expansion;
R5 leave-one-out transfer (question->nearest OTHER golden questions->their positions)."""
import sys, os, json, re, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import esrsmap as sm

class A:
    data = out = framework = None; template = 24; disclosure = 9
    conf = 0.55; floor = 0.50
    no_judge = no_judge_cache = refresh_data = refresh_embeddings = False; ssh_host = "sofi"
cfg = sm.Cfg(A()); cfg.fw_code = "GRI"
def en(x): return x.get("en", "") if isinstance(x, dict) else str(x or "")
doc = json.load(open(cfg.tmpl_file(), encoding="utf-8"))

grid = {}
def walk(n):
    if isinstance(n, dict):
        if n.get("nodeType") == "question" and n.get("displayType") == "grid":
            cols = [re.sub(r"\s+", " ", en(c.get("description"))).strip()
                    for c in (n.get("columns") or []) if isinstance(c, dict)]
            grid[n.get("nodeId")] = {"title": en(n.get("title")),
                                     "desc": re.sub(r"\s+", " ", en(n.get("description"))).strip(),
                                     "concepts": [c for c in cols if c]}
        for v in n.values(): walk(v)
    elif isinstance(n, list):
        for v in n: walk(v)
walk(doc)
sid2qid = {}
for line in open(cfg.p("disc9_sid2qid.tsv")):
    f = line.strip().split("\t");  sid2qid.update({f[0]: f[1]}) if len(f) == 2 else None
golden = collections.defaultdict(set); gtype = {}
for line in open(cfg.p("disc9_golden.tsv")):
    f = line.strip().split("\t")
    if len(f) >= 3: golden[f[0]].add(int(f[1])); gtype[int(f[1])] = f[2]
MEAS = {"Flow", "Indicator", "Asset"}

pos = sm.load_positions(cfg)
posv = sm.position_vectors(cfg, pos); pn = {k: sm._norm(v) for k, v in posv.items()}; pids = list(pn)
concs = sorted({c for g in grid.values() for c in g["concepts"]})
qtexts = {nid: (g["title"] + ". " + g["desc"])[:2000] for nid, g in grid.items()}
cv = sm.concept_vectors(cfg, concs); cn = {k: sm._norm(v) for k, v in cv.items()}
qv = sm.concept_vectors(cfg, list(qtexts.values()))
qn = {nid: sm._norm(qv[t]) for nid, t in zip(qtexts.keys(), [qtexts[k] for k in qtexts]) if t in qv}
# fix: build qn keyed by nodeId
qn = {}
qtext_vec = dict(zip(sorted(set(qtexts.values())), [None]))  # placeholder unused
qvecs = sm.concept_vectors(cfg, sorted(set(qtexts.values())))
for nid, t in qtexts.items():
    if t in qvecs: qn[nid] = sm._norm(qvecs[t])

parent = lambda pid: "/".join([x for x in pos["path"].get(pid, "").split("/") if x][:-1])
sibs = collections.defaultdict(set)
for p in pos["path"]: sibs[parent(p)].add(p)
# subtree: positions whose path starts with the parent-of-hit prefix
bypath = list(pos["path"].items())
def subtree(pid):
    pre = "/".join(pos["path"].get(pid, "").split("/")[:-2])  # grandparent prefix
    if not pre: return sibs.get(parent(pid), {pid})
    return {p for p, pa in bypath if pa.startswith(pre)}
def topk_pos(vec, k): return sorted(((p, sm._dot(vec, pn[p])) for p in pids), key=lambda x: -x[1])[:k]

# build per-question targets
Q = []
for nid, g in grid.items():
    dqid = sid2qid.get(nid)
    gm = {p for p in golden.get(dqid, set()) if gtype.get(p) in MEAS}
    if gm: Q.append((nid, g, dqid, gm))

def score(name, fn):
    NS = [20, 50, 100]; rec = {n: [] for n in NS}; seed = {n: 0 for n in NS}
    for nid, g, dqid, gm in Q:
        ranked = fn(nid, g)
        for n in NS:
            got = gm & set(ranked[:n]); rec[n].append(len(got) / len(gm)); seed[n] += 1 if got else 0
    out = " | ".join(f"@{n}: r={sum(rec[n])/len(rec[n]):.0%} seed={seed[n]/len(Q):.0%}" for n in NS)
    print(f"  {name:34} {out}")

def r_columns(nid, g, kk=3, expand=sibs):
    cand = {}
    for c in g["concepts"]:
        if c not in cn: continue
        for p, s in topk_pos(cn[c], kk):
            cand[p] = max(cand.get(p, 0), s)
            for sp in expand.get(parent(p), {p}): cand.setdefault(sp, sm._dot(cn[c], pn[sp]))
    return [p for p, _ in sorted(cand.items(), key=lambda x: -x[1])]
def r_cols_q(nid, g, kk=3):
    cand = {}
    queries = [c for c in g["concepts"] if c in cn] + ([nid] if nid in qn else [])
    for c in queries:
        vec = qn[nid] if c == nid else cn[c]
        for p, s in topk_pos(vec, kk):
            cand[p] = max(cand.get(p, 0), s)
            for sp in sibs.get(parent(p), {p}): cand.setdefault(sp, sm._dot(vec, pn[sp]))
    return [p for p, _ in sorted(cand.items(), key=lambda x: -x[1])]
def r_cols_subtree(nid, g, kk=3):
    cand = {}
    for c in g["concepts"]:
        if c not in cn: continue
        for p, s in topk_pos(cn[c], kk):
            cand[p] = max(cand.get(p, 0), s)
            for sp in subtree(p): cand.setdefault(sp, sm._dot(cn[c], pn[sp]))
    return [p for p, _ in sorted(cand.items(), key=lambda x: -x[1])]
def r_transfer(nid, g, kk=5):
    # leave-one-out: nearest OTHER grid questions by qtext, borrow their golden measurable positions
    if nid not in qn: return []
    sims = sorted(((o, sm._dot(qn[nid], qn[o])) for o in qn if o != nid), key=lambda x: -x[1])[:kk]
    cand = {}
    for o, s in sims:
        odq = sid2qid.get(o)
        for p in golden.get(odq, set()):
            if gtype.get(p) in MEAS: cand[p] = max(cand.get(p, 0), s)
    return [p for p, _ in sorted(cand.items(), key=lambda x: -x[1])]
def r_fusion(nid, g):
    a = r_cols_q(nid, g, 3); b = r_transfer(nid, g, 5)
    seen = [];
    for lst in (a, b):
        for p in lst:
            if p not in seen: seen.append(p)
    return seen

print(f"\n[sweep] {len(Q)} questions with measurable golden | {len(concs)} concepts\n")
score("R1 columns top3 +siblings", r_columns)
score("R2 columns+qtext top3 +sib", r_cols_q)
score("R3 columns top8 +siblings", lambda n, g: r_columns(n, g, kk=8))
score("R4 columns top3 +subtree", r_cols_subtree)
score("R5 transfer (LOO, k=5)", r_transfer)
score("R6 fusion cols+qtext+transfer", r_fusion)
