#!/usr/bin/env python
"""
grimap.py — GRI quantitative (grid) disclosure-question -> position mapping (CLI).

WHY THIS IS SEPARATE FROM smartmap.py
  ESRS questions carry numeric XBRL datapoint concepts, so smartmap maps concept-name -> position.
  GRI templates carry NO XBRL concepts. GRI's quantitative questions are TABLE ('grid') questions
  (matrixdynamic / matrixset) whose COLUMNS are the numeric datapoints. GRI's usable signal is its
  curated GOLDEN reference: the positions already mapped to similar GRI questions.

METHOD (chosen by measurement, not assumption — see grimap_findings notes)
  TRANSFER-CONSENSUS. For a target question, find its K most similar already-mapped GRI questions
  (by question-text embedding) and score each candidate position by the SUM of those similarities
  across the neighbours that mapped it. Positions endorsed by several near neighbours rank highest.
  Take a shortlist. Measured vs the disclosure-9 golden:
    • retrieval pool recall ~92%   • shortlist (K=5, N=8) recall ~69%, precision ~53% (F1 ~58%)
  An LLM judge was tried and REJECTED: it collapsed recall to ~12% on GRI's cryptic titles, so it is
  OFF by default and available only as an experimental precision-pruner via --judge.
  Concept (column) embedding is a weak fallback (~52% recall) used only when a question has no usable
  neighbour.

STAGES (printed as ▶ STEP n)
  extract   positions, GRI template, sid->question-id map, and the GRI golden reference
  load      grid (quantitative) questions; build the golden reference
  embed     positions, column datapoints, and question texts (text-embedding-3-large)
  map       transfer-consensus ranking + confidence gate -> shortlist  (+ optional judge prune)
  validate  per-question + aggregate recall/precision of the shortlist vs golden (when golden exists)
  report    suggestions / review queue / finalized mappings + a status-first full table

USAGE
  ./.venv-tools/bin/python smart-mapping/grimap.py run                 # full run (disclosure 9, self-validate)
  ...                                          run --shortlist 8 --transfer-k 5
  ...                                          run --no-validate       # skip golden scoring
  ...                                          run --judge             # experimental: LLM prune (lowers recall)
  ...                                          extract                 # just refresh DB extracts

Credentials/deployments come from smart-mapping/.env (same as smartmap.py).
"""
import argparse, json, re, os, sys, hashlib, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import smartmap as sm   # reuse the proven Azure client, embeddings, vector math, narration, ascii table

MEAS = {"Flow", "Indicator", "Asset"}   # measurable position types (the quantitative answer space)

# ----------------------------------------------------------------------------- config
class GriCfg(sm.Cfg):
    def __init__(self, a):
        super().__init__(a)
        self.fw_code   = "GRI"
        self.fw_name   = "Global Reporting Initiative"
        self.template  = a.template if a.template is not None else 24      # GRI 2025 template
        self.disc      = a.disclosure if a.disclosure is not None else 9   # target disclosure (has golden)
        self.ref_disc  = getattr(a, "ref_disclosure", None) or 9           # golden reference disclosure
        self.transfer_k = getattr(a, "transfer_k", None) or 5
        self.shortlist = getattr(a, "shortlist", None) or 8
        self.rel_floor = 0.50          # drop shortlist positions scoring < rel_floor * top consensus score
        self.use_judge = getattr(a, "judge", False)   # OFF by default (judge hurts recall on GRI)
        self.judge_pool = getattr(a, "judge_pool", None) or 30
        self.validate  = not getattr(a, "no_validate", False)
    def golden_file(self): return self.p(f"disc{self.ref_disc}_golden.tsv")

# ----------------------------------------------------------------------------- extraction
def extract_golden(cfg):
    """dq_id \t position_id \t position_type_name  for the reference disclosure's golden mappings."""
    open(cfg.golden_file(), "w").write(sm._sql(cfg,
        "SELECT dqp.disclosure_question_id, dqp.position_id, pt.position_type_name "
        "FROM disclosure_question_position dqp "
        "JOIN disclosure_question dq ON dq.disclosure_question_id=dqp.disclosure_question_id "
        "JOIN position p ON p.position_id=dqp.position_id AND p.term_end IS NULL "
        "JOIN position_types pt ON pt.position_type_id=p.position_type "
        f"WHERE dq.disclosure_id={cfg.ref_disc};"))

# ----------------------------------------------------------------------------- loaders
def _en(x): return x.get("en", "") if isinstance(x, dict) else str(x or "")
def _clean(s): return re.sub(r"\s+", " ", s or "").strip()

def load_grid_questions(cfg):
    """GRI quantitative questions = grid questions (matrixdynamic/matrixset)."""
    doc = json.load(open(cfg.tmpl_file(), encoding="utf-8"))
    grid, st = [], {"total": 0, "grid": 0, "nongrid": 0}
    def walk(n):
        if isinstance(n, dict):
            if n.get("nodeType") == "question":
                st["total"] += 1
                if n.get("displayType") == "grid":
                    st["grid"] += 1
                    cols = [_clean(_en(c.get("description"))) for c in (n.get("columns") or []) if isinstance(c, dict)]
                    cols = [c for c in cols if c]
                    title, desc = _clean(_en(n.get("title"))), _clean(_en(n.get("description")))
                    grid.append({"nodeId": n.get("nodeId"), "ref": title, "desc": desc[:600],
                                 "concepts": cols, "qtext": (title + ". " + desc)[:2000]})
                else:
                    st["nongrid"] += 1
            for v in n.values(): walk(v)
        elif isinstance(n, list):
            for v in n: walk(v)
    walk(doc)
    return grid, st

def load_golden(cfg):
    golden, gtype = collections.defaultdict(set), {}
    fp = cfg.golden_file()
    if not os.path.exists(fp): return golden, gtype
    for line in open(fp, encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").split("\t")
        if len(f) >= 3 and f[1].isdigit():
            golden[f[0]].add(int(f[1])); gtype[int(f[1])] = f[2]
    return golden, gtype

# ----------------------------------------------------------------------------- intro
def print_intro(cfg):
    L = "=" * 78
    print(L)
    print("SoFi Smart-Mapping  —  GRI quantitative (table) question → ESG metric ('position') mapper")
    print(L)
    print("WHAT THIS DOES")
    print("    GRI quantitative questions are TABLE ('grid') questions whose columns collect numbers.")
    print("    For each, it proposes the internal SoFi metric(s) ('positions') that answer it.")
    print("REGULATORY FRAMEWORK")
    print(f"    {cfg.fw_name} — template {cfg.template}, target disclosure {cfg.disc}, "
          f"golden reference disclosure {cfg.ref_disc}.")
    print("METHOD (GRI has no XBRL concepts, but it HAS curated golden data)")
    print(f"    TRANSFER-CONSENSUS: rank positions by agreement across the {cfg.transfer_k} most similar")
    print("    already-mapped GRI questions; take a shortlist. (Measured ~69% recall / ~53% precision")
    print("    vs golden. An LLM judge was tested and rejected — it cut recall to ~12%; enable with --judge.)")
    print("DATA SOURCES (rebuilt every run — nothing cached except judge verdicts)")
    print(f"    • SoFi MySQL via ssh '{cfg.ssh_host}': positions, GRI template, golden reference mappings")
    print(f"    • Azure OpenAI — embeddings: {cfg.emb_dep}"
          + (f";  judge: {cfg.chat_dep} (temp={cfg.temperature})" if cfg.use_judge else ";  judge: OFF"))
    print("RESULT STATUSES")
    print("    MAPPED  = position(s) proposed   REVIEW = no confident neighbour (weak match)")
    print("    GAP     = (only with --judge) judge rejected every candidate")
    print(L)

# ----------------------------------------------------------------------------- pipeline
def run(cfg):
    sm._STEP[0] = 0
    print_intro(cfg)

    sm.step("Extract source data from the SoFi database (always fresh, via ssh)")
    sm.extract_data(cfg)            # positions + GRI template + sid->qid (reused from smartmap)
    extract_golden(cfg)             # + GRI golden reference
    sm.info(f"golden reference: {sum(1 for _ in open(cfg.golden_file()))} links from disclosure {cfg.ref_disc}")

    sm.step("Load positions and GRI grid (quantitative) questions")
    pos = sm.load_positions(cfg)
    sm.info(f"{len(pos['name'])} active positions loaded")
    sid2qid = sm.load_sid2qid(cfg)
    grid, st = load_grid_questions(cfg)
    sm.info(f"template {cfg.template}: {st['total']} question nodes; "
            f"{st['grid']} grid (QUANTITATIVE), {st['nongrid']} non-grid (narrative/other)")
    golden, gtype = load_golden(cfg)
    gmeas = {dq: {p for p in ps if gtype.get(p) in MEAS} for dq, ps in golden.items()}
    sm.info(f"==> processing {len(grid)} GRI quantitative questions")

    sm.step(f"Embed positions with {cfg.emb_dep}")
    posv = sm.position_vectors(cfg, pos); pn = {k: sm._norm(v) for k, v in posv.items()}; pids = list(pn)

    sm.step("Embed column datapoints + question texts")
    concs = sorted({c for g in grid for c in g["concepts"]})
    cv = sm.concept_vectors(cfg, concs); cn = {k: sm._norm(v) for k, v in cv.items()}
    qtexts = sorted({g["qtext"] for g in grid})
    qv = sm.concept_vectors(cfg, qtexts); qn_by_text = {t: sm._norm(v) for t, v in qv.items()}
    qn = {g["nodeId"]: qn_by_text[g["qtext"]] for g in grid if g["qtext"] in qn_by_text}
    sm.info(f"{len(concs)} column datapoints + {len(qtexts)} question texts embedded")

    parent = lambda pid: "/".join([x for x in pos["path"].get(pid, "").split("/") if x][:-1])
    sibs = collections.defaultdict(set)
    for p in pos["path"]: sibs[parent(p)].add(p)
    def topk_pos(vec, k): return sorted(((p, sm._dot(vec, pn[p])) for p in pids), key=lambda x: -x[1])[:k]

    # reference set for transfer: grid questions (in ref disclosure) that have measurable golden
    ref_nodes = [g["nodeId"] for g in grid if gmeas.get(sid2qid.get(g["nodeId"])) and g["nodeId"] in qn]

    sm.step(f"Map: transfer-consensus over {cfg.transfer_k} nearest mapped questions → shortlist (≤{cfg.shortlist}); gate at sim≥{cfg.conf}")
    confident, lowconf = [], []
    for g in grid:
        nid = g["nodeId"]; dqid = sid2qid.get(nid)
        # nearest OTHER reference questions by question-text similarity
        sims = []
        if nid in qn:
            sims = sorted(((o, sm._dot(qn[nid], qn[o])) for o in ref_nodes if o != nid),
                          key=lambda x: -x[1])[:cfg.transfer_k]
        # consensus: score each measurable golden position by summed neighbour similarity
        score = collections.defaultdict(float)
        for onid, s in sims:
            for p in gmeas.get(sid2qid.get(onid), set()):
                if p in pn: score[p] += s
        ranked = sorted(score.items(), key=lambda x: -x[1])
        top_sim = sims[0][1] if sims else 0.0
        # concept fallback pool (used only as nearest-hint when no confident neighbour)
        concept_hint = []
        if not ranked or top_sim < cfg.conf:
            cand = {}
            for c in g["concepts"]:
                if c not in cn: continue
                for p, sc in topk_pos(cn[c], 3): cand[p] = max(cand.get(p, 0.0), sc)
            concept_hint = sorted(cand.items(), key=lambda x: -x[1])[:5]
        rec = {"nodeId": nid, "dq_id": dqid, "ref": g["ref"], "desc": g["desc"], "concepts": g["concepts"],
               "top_sim": round(top_sim, 3), "ranked": ranked, "hint": concept_hint}
        (confident if (ranked and top_sim >= cfg.conf) else lowconf).append(rec)
    sm.info(f"confident (neighbour sim ≥ {cfg.conf}): {len(confident)} | weak → review: {len(lowconf)}")

    # final selection = consensus shortlist (top-N above relative floor)
    for r in confident:
        topscore = r["ranked"][0][1] if r["ranked"] else 0.0
        sel = [(p, s) for p, s in r["ranked"][:cfg.shortlist] if s >= cfg.rel_floor * topscore]
        r["selected"] = [{"position_id": p, "name": pos["name"].get(p, ""),
                          "score": round(s / max(cfg.transfer_k, 1), 3)} for p, s in sel]

    finalized = [{"nodeId": r["nodeId"], "dq_id": r["dq_id"], "ref": r["ref"],
                  "selected": r["selected"], "reasoning": "transfer-consensus"} for r in confident]
    if cfg.use_judge and confident:
        finalized = judge_prune(cfg, pos, confident)

    sm.step("Write reports and render the full report table")
    write_reports(cfg, pos, grid, confident, lowconf, finalized)
    summary(cfg, grid, confident, lowconf, finalized)
    if cfg.validate and golden:
        validate(cfg, grid, sid2qid, gmeas, confident, finalized)
    print_full_table(cfg, pos, confident, lowconf, finalized)

# ----------------------------------------------------------------------------- optional judge prune (experimental)
def judge_prune(cfg, pos, confident):
    """EXPERIMENTAL: ask gpt-5.4 to keep only the truly-fitting positions from the consensus shortlist.
    Lowers recall on GRI (cryptic titles); off by default."""
    cache_fp = cfg.p("gri_judge_cache.json")
    jcache = json.load(open(cache_fp)) if (cfg.judge_cache and os.path.exists(cache_fp)) else {}
    cli = sm._client()
    SYS = ("You are an ESG reporting expert. From the CANDIDATE positions already shortlisted for a GRI "
           "quantitative table question, KEEP only those that genuinely capture the question's measurable "
           "datapoints; drop the rest. Only use candidate IDs. Respond JSON {\"selected\":[ids]}.")
    sm.step(f"EXPERIMENTAL judge prune ({cfg.chat_dep}, temp={cfg.temperature}) over {len(confident)} questions")
    finalized = []
    for i, r in enumerate(confident, 1):
        pool = r["selected"]; poolids = {s["position_id"] for s in pool}
        key = hashlib.sha256(json.dumps({"m": cfg.chat_dep, "t": cfg.temperature, "n": r["nodeId"],
                                         "pool": sorted(poolids)}, sort_keys=True).encode()).hexdigest()
        if cfg.judge_cache and key in jcache:
            keep = [p for p in jcache[key] if p in poolids]
        else:
            lines = [f"id={s['position_id']} | {s['name']}" for s in pool]
            user = (f"GRI QUESTION {r['ref']}\nColumns: {', '.join(r['concepts'])[:500]}\n"
                    f"Requirement: {r['desc']}\n\nCANDIDATES:\n" + "\n".join(lines))
            try:
                resp = cli.chat.completions.create(model=cfg.chat_dep, temperature=cfg.temperature,
                    messages=[{"role": "system", "content": SYS}, {"role": "user", "content": user}],
                    response_format={"type": "json_object"})
                keep = [int(x) for x in json.loads(resp.choices[0].message.content).get("selected", []) if int(x) in poolids]
            except Exception as e:
                keep = list(poolids)   # on error, keep consensus shortlist unchanged
            jcache[key] = keep
        finalized.append({"nodeId": r["nodeId"], "dq_id": r["dq_id"], "ref": r["ref"],
                          "selected": [s for s in pool if s["position_id"] in keep], "reasoning": "judge-pruned"})
        sm.info(f"[{i}/{len(confident)}] {sm._trunc(r['ref'],28):28} → kept {len(keep)}/{len(pool)}")
    if cfg.judge_cache: json.dump(jcache, open(cache_fp, "w"), indent=0)
    return finalized

# ----------------------------------------------------------------------------- validation vs golden
def validate(cfg, grid, sid2qid, gmeas, confident, finalized):
    print("\n" + "-" * 78)
    print(f"VALIDATION vs GRI golden (disclosure {cfg.ref_disc}, measurable positions only)")
    print("-" * 78)
    fin_by_node = {r["nodeId"]: r for r in finalized}
    pool_by_node = {r["nodeId"]: {p for p, _ in r["ranked"]} for r in confident}
    recs, precs, pool_recs = [], [], []; n = 0
    for g in grid:
        nid = g["nodeId"]; gold = gmeas.get(sid2qid.get(nid), set())
        if not gold: continue
        n += 1
        pool_recs.append(len(gold & pool_by_node.get(nid, set())) / len(gold))
        fr = fin_by_node.get(nid)
        sel = {s["position_id"] for s in fr["selected"]} if fr else set()
        if sel:
            recs.append(len(gold & sel) / len(gold)); precs.append(len(gold & sel) / len(sel))
    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
    f1 = (lambda r, p: 2 * r * p / (r + p) if r + p else 0.0)(avg(recs), avg(precs))
    print(f"  questions with golden            : {n}")
    print(f"  retrieval recall (consensus pool): {avg(pool_recs):.1%}  (ceiling for the shortlist)")
    print(f"  FINAL recall (shortlist)         : {avg(recs):.1%}  over {len(recs)} mapped questions")
    print(f"  FINAL precision (shortlist)      : {avg(precs):.1%}")
    print(f"  FINAL F1                         : {f1:.1%}")
    print("-" * 78)

# ----------------------------------------------------------------------------- reports + table
def write_reports(cfg, pos, grid, confident, lowconf, finalized):
    fin_by_node = {r["nodeId"]: r for r in finalized}
    with open(cfg.report_file("suggestions"), "w", encoding="utf-8") as f:
        f.write(f"# GRI (template {cfg.template}) — quantitative position suggestions\n\n")
        f.write(f"{len(confident)}/{len(grid)} grid questions mapped (transfer-consensus).\n\n")
        for r in confident:
            sel = fin_by_node.get(r["nodeId"], {}).get("selected", [])
            f.write(f"## {r['ref']}  (dq_id={r['dq_id']})\n- columns: {', '.join(r['concepts'])[:200]}\n")
            for s in sel: f.write(f"  - [{s['score']}] {s['position_id']} — {s['name']}\n")
            f.write("\n")
    with open(cfg.report_file("review"), "w", encoding="utf-8") as f:
        f.write(f"# GRI (template {cfg.template}) — review queue\n\n## Weak / no confident neighbour: {len(lowconf)}\n")
        for r in lowconf:
            f.write(f"- **{r['ref']}** (dq_id={r['dq_id']}) top_sim={r['top_sim']} "
                    f"concept-hint={[(p, round(s,2)) for p, s in r['hint']]}\n")
    json.dump(finalized, open(cfg.report_file("final", "json"), "w"), indent=1)
    with open(cfg.report_file("final"), "w", encoding="utf-8") as f:
        f.write(f"# GRI (template {cfg.template}) — finalized mappings ({finalized[0]['reasoning'] if finalized else 'n/a'})\n\n")
        for r in finalized:
            if not r["selected"]: continue
            f.write(f"## {r['ref']}  (dq_id={r['dq_id']})\n")
            for s in r["selected"]: f.write(f"  - {s['position_id']} — {s['name']} [{s['score']}]\n")
            f.write("\n")

def print_full_table(cfg, pos, confident, lowconf, finalized):
    fin_by_node = {r["nodeId"]: r for r in finalized}
    rows = []
    for r in confident:
        sel = fin_by_node.get(r["nodeId"], {}).get("selected", [])
        if sel:
            first = True
            for s in sel:
                rows.append(["MAPPED" if first else "", r["ref"][:30] if first else "",
                             (r["dq_id"] or "") if first else "",
                             f"{s['position_id']} {sm._trunc(pos['name'].get(s['position_id'],''),38)}",
                             f"{s['score']:.2f}"]); first = False
        else:
            rows.append(["GAP", r["ref"][:30], r["dq_id"] or "", "judge rejected all candidates", f"{r['top_sim']:.2f}"])
    for r in lowconf:
        hint = r["hint"][0][0] if r["hint"] else "-"
        rows.append(["REVIEW", r["ref"][:30], r["dq_id"] or "", f"no confident neighbour · hint {hint}", f"{r['top_sim']:.2f}"])
    print("\n" + "-" * 78)
    print("WHAT 'SCORE' MEANS HERE")
    print("-" * 78)
    print("  SCORE (0.00-1.00) is a transfer-consensus strength: how strongly the nearest already-mapped")
    print("  GRI questions agree on this position. It is NOT an AI/LLM confidence; treat the result as a")
    print("  ranked review queue (measured ~69% recall / ~53% precision vs the GRI golden).")
    print("-" * 78)
    print("\nFULL REPORT  (every GRI quantitative question, with status)")
    print(sm._ascii_table(["STATUS", "QUESTION", "DQ_ID", "ANSWER POSITION", "SCORE"], rows))
    print("  STATUS: MAPPED = position(s) proposed · REVIEW = no confident neighbour · GAP = judge rejected all (--judge)")

def summary(cfg, grid, confident, lowconf, finalized):
    fin = [r for r in finalized if r["selected"]]
    print("\n" + "=" * 60)
    print(f"GRI template {cfg.template} (disc {cfg.disc}, ref {cfg.ref_disc})  |  "
          f"embed={cfg.emb_dep}  selector={'judge-prune' if cfg.use_judge else 'transfer-consensus'}")
    print(f"  GRI quantitative (grid) questions : {len(grid)}")
    print(f"  mapped                            : {len(fin)}")
    print(f"  weak → review                     : {len(lowconf)}")
    if cfg.use_judge:
        print(f"  judge-rejected (GAP)              : {len(confident) - len(fin)}")
    print(f"  reports -> {os.path.basename(cfg.report_file('suggestions'))}, "
          f"{os.path.basename(cfg.report_file('review'))}, {os.path.basename(cfg.report_file('final'))}")
    print("=" * 60)

# ----------------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description="GRI quantitative (grid) question -> position mapping pipeline "
                                             "(transfer-consensus, validated against GRI golden)")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("run", "extract"):
        sp = sub.add_parser(name)
        sp.add_argument("--data"); sp.add_argument("--out")
        sp.add_argument("--template", type=int, default=None, help="GRI disclosure_template_id (default 24)")
        sp.add_argument("--disclosure", type=int, default=None, help="target disclosure_id (default 9)")
        sp.add_argument("--ref-disclosure", type=int, default=None, dest="ref_disclosure",
                        help="golden reference disclosure_id (default 9)")
        sp.add_argument("--transfer-k", type=int, default=None, dest="transfer_k",
                        help="# nearest mapped questions to transfer from (default 5)")
        sp.add_argument("--shortlist", type=int, default=None, help="max positions per question (default 8)")
        sp.add_argument("--conf", type=float, default=0.55, help="neighbour-similarity gate (default 0.55)")
        sp.add_argument("--judge", action="store_true", help="EXPERIMENTAL: LLM prune of the shortlist (lowers recall)")
        sp.add_argument("--no-judge-cache", action="store_true")
        sp.add_argument("--no-validate", action="store_true", help="skip scoring against golden")
        sp.add_argument("--judge-pool", type=int, default=None, dest="judge_pool")
        sp.add_argument("--floor", type=float, default=0.50, help=argparse.SUPPRESS)
        sp.add_argument("--no-judge", action="store_true", help=argparse.SUPPRESS)  # accepted, ignored (judge off by default)
        sp.add_argument("--refresh-data", action="store_true")
        sp.add_argument("--refresh-embeddings", action="store_true")
        sp.add_argument("--ssh-host", default="sofi")
        sp.add_argument("--framework", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args()
    if not a.cmd: ap.print_help(); return
    cfg = GriCfg(a)
    if a.cmd == "extract":
        cfg.refresh_data = True; sm.extract_data(cfg); extract_golden(cfg)
        print(f"[extract] GRI template {cfg.template} + golden reference (disc {cfg.ref_disc}) written to {cfg.data}")
    elif a.cmd == "run":
        run(cfg)

if __name__ == "__main__":
    main()
