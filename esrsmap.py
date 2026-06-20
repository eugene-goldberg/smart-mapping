#!/usr/bin/env python
"""
esrsmap.py — ESRS quantitative disclosure-question -> position mapping (CLI).

Consolidates the validated pipeline into one program. When invoked it reproduces the
ESRS-2026 quantitative mapping run: 42 metric questions -> 39 confident -> gpt-5.4 judge ->
finalized mappings, with parameter / low-confidence / judge abstentions routed to a review queue.

STAGES
  load        positions (name/path/type/unit), ESRS template concepts, sid->question-id map
  embed       Azure text-embedding-3-large for positions + numeric concepts (cached on disk)
  classify    extract numeric XBRL concepts; drop parameter-numerics (TimeHorizon/InYears/Date...)
  retrieve    concept-name -> top-3 positions + sibling expansion -> candidate pool
  gate        abstain-first: top-1 >= CONF to show; weak candidates (< FLOOR) suppressed
  judge       gpt-5.4 selects the precise variant cluster per confident question (skippable)
  report      reporter suggestions, curator review queue, finalized mappings

USAGE
  ./.venv-tools/bin/python smart-mapping/esrsmap.py run                 # full run (uses caches)
  ...                                          run --no-judge            # skip LLM judge
  ...                                          run --refresh-data        # re-pull from DB via ssh
  ...                                          run --refresh-embeddings  # re-embed positions
  ...                                          run --template 27 --disclosure 5 --conf 0.55 --floor 0.50

Credentials/deployments come from smart-mapping/.env:
  AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION,
  AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME (text-embedding-3-large), AZURE_OPENAI_DEPLOYMENT_NAME (gpt-5.4)
"""
import argparse, json, re, math, os, sys, time, subprocess, hashlib
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(HERE, ".env"))

# ----------------------------------------------------------------------------- config
class Cfg:
    def __init__(self, a):
        self.data    = a.data or os.path.join(HERE, "scratch")
        self.out     = a.out  or os.path.join(HERE, "scratch")
        self.template= a.template            # disclosure_template_id (ESRS 2026 = 27)
        self.disc    = a.disclosure          # disclosure_id holding the instantiated questions (= 5)
        self.conf    = a.conf                # confidence gate (top-1)
        self.floor   = a.floor               # per-candidate floor within confident questions
        self.topk    = 3                     # positions retrieved per concept
        self.judge_pool = 12                 # candidates handed to the judge
        self.use_judge  = not a.no_judge
        self.judge_cache = not getattr(a, "no_judge_cache", False)
        self.refresh_data = a.refresh_data
        self.refresh_emb  = a.refresh_embeddings
        self.ssh_host = a.ssh_host
        self.framework= getattr(a, "framework", None)   # framework name/abbrev (resolved in main)
        self.fw_id    = None                             # disclosure_framework_id once resolved
        self.fw_name  = None                             # display name once resolved
        self.fw_code  = "ESRS"                           # short label used in banners + filenames
        self.emb_dep  = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") or "text-embedding-3-large"
        self.chat_dep = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME") or "gpt-5.4"
        self.temperature = float(os.getenv("AZURE_OPENAI_TEMPERATURE", "0"))
    def p(self, name): return os.path.join(self.data, name)
    def o(self, name): return os.path.join(self.out, name)
    def slug(self): return self.fw_code.lower()                       # filename prefix (esrs, gri, ...)
    def tmpl_file(self): return self.p(f"{self.slug()}_tmpl{self.template}.json")
    def report_file(self, kind, ext="md"): return self.o(f"{self.slug()}{self.template}_{kind}.{ext}")

# ----------------------------------------------------------------------------- azure client
def _client():
    from openai import AzureOpenAI
    key, ep = os.getenv("AZURE_OPENAI_API_KEY"), os.getenv("AZURE_OPENAI_ENDPOINT")
    if not key or not ep: sys.exit("Missing Azure creds in smart-mapping/.env")
    return AzureOpenAI(api_key=key, azure_endpoint=ep,
                       api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"))

# ----------------------------------------------------------------------------- db extraction (optional)
def _sql(cfg, query, utf8=True):
    flags = "--default-character-set=utf8mb4 " if utf8 else ""
    remote = f'docker exec sofi_mysql mysql -uroot -psofi sofi {flags}--raw -N -B -e "{query}"'
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", cfg.ssh_host, remote],
                       capture_output=True, text=True)
    return "\n".join(l for l in r.stdout.splitlines()
                     if "post-quantum" not in l and not l.startswith("**") and "store now" not in l)

def extract_data(cfg):
    print("[extract] pulling positions / template / sid-map from DB ...")
    open(cfg.p("pos_text.tsv"), "w").write(_sql(cfg,
        "SELECT p.position_id, REPLACE(REPLACE(pd.name,CHAR(9),' '),CHAR(10),' '), "
        "REPLACE(REPLACE(COALESCE(pd.description,''),CHAR(9),' '),CHAR(10),' ') "
        "FROM position p JOIN position_index pi ON pi.position_id=p.position_id "
        "JOIN position_dict pd ON pd.position_id=p.position_id AND pd.term_start=p.term_start AND pd.language_id=2 "
        "WHERE p.term_end IS NULL;"))
    open(cfg.p("pos_attrs.tsv"), "w").write(_sql(cfg,
        "SELECT p.position_id, COALESCE(p.parent_position_id,0), pt.position_type_name, "
        "COALESCE(p.unit_class_id,0), p.use_in_report, p.path "
        "FROM position p JOIN position_types pt ON pt.position_type_id=p.position_type WHERE p.term_end IS NULL;"))
    open(cfg.p("pos_unitclass.tsv"), "w").write(_sql(cfg,
        "SELECT p.position_id, COALESCE(ucd.name,'') FROM position p "
        "LEFT JOIN unit_class_dict ucd ON ucd.unit_class_id=p.unit_class_id AND ucd.language_id=2 WHERE p.term_end IS NULL;"))
    open(cfg.tmpl_file(), "w").write(_sql(cfg,
        f"SELECT content FROM disclosure_template WHERE disclosure_template_id={cfg.template};"))
    open(cfg.p(f"disc{cfg.disc}_sid2qid.tsv"), "w").write(_sql(cfg,
        f"SELECT template_question_sid, disclosure_question_id FROM disclosure_question WHERE disclosure_id={cfg.disc};"))

# ----------------------------------------------------------------------------- framework resolution
def list_frameworks(cfg):
    """[(framework_id, name)] for all regulatory frameworks on record."""
    out = _sql(cfg,
        "SELECT f.disclosure_framework_id, d.name FROM disclosure_framework f "
        "JOIN disclosure_framework_dict d ON d.disclosure_framework_id=f.disclosure_framework_id "
        "AND d.language_id=2 ORDER BY f.disclosure_framework_id;")
    fws = []
    for line in out.splitlines():
        f = line.split("\t")
        if len(f) >= 2 and f[0].strip().isdigit():
            fws.append((int(f[0]), f[1].strip()))
    return fws

def framework_code(name):
    """Short uppercase label for banners/filenames: parenthetical abbrev, else word-initials, else alnum.
    e.g. 'European ... (ESRS)'->ESRS, 'Global Reporting Initiative'->GRI, 'SB 253'->SB253."""
    m = re.search(r"\(([^)]+)\)", name)
    if m: return re.sub(r"[^A-Za-z0-9]+", "", m.group(1)).upper()
    words = re.findall(r"[A-Za-z]+", name)
    if len(words) >= 2: return "".join(w[0] for w in words).upper()
    return re.sub(r"[^A-Za-z0-9]+", "", name).upper()

def resolve_framework(cfg, query):
    """Map a framework name/abbreviation to (fw_id, name, template_id, disclosure_id, year, n_questions).

    Matches on the full localized name, a substring either way, or the word-initials of the
    name (so 'GRI'->Global Reporting Initiative, 'CDP'->Carbon Disclosure Project work even
    though those abbreviations aren't stored). Picks the latest-year template for that framework
    and, within it, the disclosure carrying the most questions (the real mapping target)."""
    fws = list_frameworks(cfg)
    if not fws:
        sys.exit("[framework] could not read frameworks from DB (is the ssh host reachable?)")
    norm   = lambda s: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()
    initials = lambda name: "".join(w[0] for w in re.findall(r"[A-Za-z]+", re.sub(r"\(.*?\)", "", name))).lower()
    q = norm(query); qz = q.replace(" ", "")
    def is_hit(name):
        n = norm(name)
        if not q: return False
        if q == n or q == initials(name) or qz == n.replace(" ", ""): return True
        return len(q) >= 3 and (q in n or n in q)   # loose substring only for 3+ chars
    hits = [(fid, name) for fid, name in fws if is_hit(name)]
    avail = " | ".join(f"{fid}:{name}" for fid, name in fws)
    if not hits:
        sys.exit(f"[framework] no match for '{query}'.\n  Available: {avail}")
    if len(hits) > 1:
        sys.exit(f"[framework] '{query}' is ambiguous: {' | '.join(n for _, n in hits)}\n  Available: {avail}")
    fid, name = hits[0]
    pick = _sql(cfg,
        "SELECT d.disclosure_template_id, d.disclosure_id, t.year, COUNT(dq.disclosure_question_id) "
        "FROM disclosure d JOIN disclosure_template t ON t.disclosure_template_id=d.disclosure_template_id "
        "LEFT JOIN disclosure_question dq ON dq.disclosure_id=d.disclosure_id "
        f"WHERE t.disclosure_framework_id={fid} "
        "GROUP BY d.disclosure_id, d.disclosure_template_id, t.year "
        "ORDER BY t.year DESC, COUNT(dq.disclosure_question_id) DESC;")
    rows = [r.split("\t") for r in pick.splitlines() if r and r.split("\t")[0].strip().isdigit()]
    if not rows:
        sys.exit(f"[framework] '{name}' (id {fid}) has no disclosures with questions to map.")
    tmpl, disc, year, nq = int(rows[0][0]), int(rows[0][1]), rows[0][2], int(rows[0][3])
    return fid, name, tmpl, disc, year, nq

# ----------------------------------------------------------------------------- loaders
def load_positions(cfg):
    name, path, ptype, parent = {}, {}, {}, {}
    rec = re.compile(r'^(\d+)\t'); last = None; desc = {}
    for raw in open(cfg.p("pos_text.tsv"), encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n").rstrip("\r"); m = rec.match(line)
        if m:
            a = line.split("\t"); pid = int(a[0]); name[pid] = a[1] if len(a) > 1 else ""
            desc[pid] = a[2] if len(a) > 2 else ""; last = pid
        elif last is not None: desc[last] += " " + line
    unit = {}
    for line in open(cfg.p("pos_unitclass.tsv"), encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").rstrip("\r").split("\t")
        if f and f[0].isdigit(): unit[int(f[0])] = f[1] if len(f) > 1 else ""
    for line in open(cfg.p("pos_attrs.tsv"), encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").rstrip("\r").split("\t")
        if len(f) >= 6: path[int(f[0])] = f[5]; ptype[int(f[0])] = f[2]; parent[int(f[0])] = int(f[1])
    return {"name": name, "desc": desc, "path": path, "type": ptype, "unit": unit, "parent": parent}

def load_sid2qid(cfg):
    m = {}
    fp = cfg.p(f"disc{cfg.disc}_sid2qid.tsv")
    if os.path.exists(fp):
        for line in open(fp):
            f = line.strip().split("\t")
            if len(f) == 2: m[f[0]] = f[1]
    return m

# ----------------------------------------------------------------------------- concept classification
NUM   = re.compile(r'(Percentage|Number|Amount|Tonnes|Monetary|Rate|InYears|Quantity|Weight|Volume|Area|Energy|Proportion|Share|Gross|Consumption|Intensity|Emissions|Hours|Ratio|Revenue|Cost|Capex|Opex|Expenditure|Water|Discharge|Stored|Recycled|Reused)')
NARR  = re.compile(r'(Explanatory|Description|Disclosure|Information)')
STRUCT= re.compile(r'(Axis|Member|LineItems|Table|Hypercube|Domain)')
PARAM = re.compile(r'(TimeHorizon|InYearsCountedFromReportingPeriod|InYears|^Date|DateOf|Version|YearOf|NumberOfYears)')
def is_num(c):
    n = c.split(":", 1)[-1]
    return bool(NUM.search(n)) and not STRUCT.search(n) and not NARR.search(n) and not PARAM.search(n)
def looks_numeric(c):
    n = c.split(":", 1)[-1]
    return bool(NUM.search(n)) and not STRUCT.search(n) and not NARR.search(n)
def humanize(c):
    n = c.split(":", 1)[-1]
    n = re.sub(r'(?<=[a-z])(?=[A-Z])', " ", n)
    n = re.sub(r'(?<=[A-Za-z])(?=[0-9])', " ", n)
    n = re.sub(r'(?<=[0-9])(?=[A-Za-z])', " ", n)
    return n
def _en(x): return x.get("en", "") if isinstance(x, dict) else str(x)

def load_quant_questions(cfg):
    """Returns (quant[list], abstain_param[list], stats[dict]) from the disclosure template content tree."""
    doc = json.load(open(cfg.tmpl_file(), encoding="utf-8"))
    quant, abstain = [], []
    st = {"total": 0, "datapoint": 0, "quant": 0, "param": 0, "qual": 0}
    def walk(n):
        if isinstance(n, dict):
            if n.get("nodeType") == "question":
                st["total"] += 1
                cs = [c for c in (n.get("xbrlConcepts") or []) if isinstance(c, str)]
                nums = [c for c in cs if is_num(c)]
                if cs: st["datapoint"] += 1
                node = {"nodeId": n.get("nodeId"), "ref": _en(n.get("title")),
                        "desc": _en(n.get("description"))[:600], "concepts": nums}
                if nums:
                    quant.append(node); st["quant"] += 1
                elif any(looks_numeric(c) for c in cs):
                    abstain.append({"ref": _en(n.get("title")),
                                    "param_concepts": [humanize(c) for c in cs if looks_numeric(c)]})
                    st["param"] += 1
                elif cs:
                    st["qual"] += 1
            for v in n.values(): walk(v)
        elif isinstance(n, list):
            for v in n: walk(v)
    walk(doc)
    return quant, abstain, st

# ----------------------------------------------------------------------------- embeddings (cached)
def _embed(cfg, texts):
    cli = _client(); out = []
    for i in range(0, len(texts), 128):
        b = texts[i:i + 128]
        for attempt in range(6):
            try:
                r = cli.embeddings.create(model=cfg.emb_dep, input=[t[:8000] or " " for t in b]); break
            except Exception as e:
                if attempt == 5: raise
                time.sleep(2 ** attempt)
        out.extend(d.embedding for d in r.data)
    return out

def position_vectors(cfg, pos):
    # Always embed fresh from source text (no cached vectors are trusted).
    ids = [p for p in pos["name"] if p in pos["path"]]
    info(f"embedding {len(ids)} positions from rich text (name + description + lineage + unit + type)")
    def lineage(pid):
        segs = [int(x) for x in pos["path"][pid].split("/") if x]
        return " > ".join(pos["name"].get(s, "") for s in segs[:-1] if pos["name"].get(s, ""))
    def rich(pid):
        parts = [pos["name"][pid]]
        if pos["desc"].get(pid): parts.append(pos["desc"][pid].strip())
        if lineage(pid): parts.append("Category: " + lineage(pid))
        if pos["unit"].get(pid): parts.append("Unit: " + pos["unit"][pid])
        if pos["type"].get(pid): parts.append("Type: " + pos["type"][pid])
        return re.sub(r"\s+", " ", " . ".join(parts)).strip()
    vecs = _embed(cfg, [rich(p) for p in ids])
    info(f"received {len(vecs)} position vectors ({len(vecs[0]) if vecs else 0}-dim)")
    return {p: v for p, v in zip(ids, vecs)}

def concept_vectors(cfg, concepts):
    uniq = sorted(set(concepts))
    return dict(zip(uniq, _embed(cfg, uniq)))

# ----------------------------------------------------------------------------- vector math
def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]
def _dot(a, b): return sum(x * y for x, y in zip(a, b))

# ----------------------------------------------------------------------------- narration
_STEP = [0]
def step(msg):
    _STEP[0] += 1
    print(f"\n▶ STEP {_STEP[0]}: {msg}")
def info(msg):
    print(f"    · {msg}")

def print_intro(cfg):
    L = "=" * 78
    print(L)
    print(f"SoFi Smart-Mapping  —  {cfg.fw_code} quantitative question → ESG metric ('position') mapper")
    print(L)
    print("WHAT THIS DOES")
    print(f"    For each {cfg.fw_code} disclosure question that asks for a NUMBER, it finds the internal")
    print("    SoFi metric(s) ('positions') that answer it — or flags that none exists yet.")
    print("REGULATORY FRAMEWORK")
    print(f"    {cfg.fw_name or 'ESRS (European Sustainability Reporting Standards)'} "
          f"— template {cfg.template}, disclosure {cfg.disc}.")
    print("QUESTION TYPES (this run handles QUANTITATIVE only)")
    if cfg.fw_code == "ESRS":
        print("    ESRS questions are ~55% qualitative (narrative: policies, processes, targets) and")
        print("    ~45% quantitative (numeric: emissions, energy, headcount). We process the numeric")
        print("    ones, identified by their numeric XBRL datapoint concept; narrative ones are out of scope.")
    else:
        print("    Disclosure questions split into qualitative (narrative) and quantitative (numeric).")
        print("    We process the numeric ones, identified by their numeric XBRL datapoint concept;")
        print(f"    narrative ones are out of scope. NOTE: this matcher is tuned to ESRS XBRL datapoints,")
        print(f"    so a non-ESRS framework like {cfg.fw_code} may surface few or no quantitative questions.")
    print("DATA SOURCES (rebuilt every run — nothing cached)")
    print(f"    • SoFi MySQL via ssh '{cfg.ssh_host}': positions, {cfg.fw_code} template content, question→id map")
    print(f"    • Azure OpenAI — embeddings: {cfg.emb_dep};  judge: {cfg.chat_dep if cfg.use_judge else 'OFF (--no-judge)'} (temp={cfg.temperature})")
    print("METHOD")
    print("    embed concept names + positions → semantic match → expand variant siblings →")
    print(f"    confidence gate (abstain if top score < {cfg.conf}) → LLM judge picks the final variant cluster.")
    print("RESULT STATUSES")
    print("    MAPPED  = position(s) found      GAP    = numeric metric but no position exists")
    print("    REVIEW  = match too weak         SKIP   = reporting parameter, not a metric")
    print(L)

# ----------------------------------------------------------------------------- the pipeline
def run(cfg):
    _STEP[0] = 0
    print_intro(cfg)

    step("Extract source data from the SoFi database (always fresh, via ssh)")
    extract_data(cfg)

    step(f"Load & parse positions and the {cfg.fw_code} disclosure template")
    pos = load_positions(cfg)
    info(f"{len(pos['name'])} active positions loaded (name, hierarchy path, type, unit-class)")
    sid2qid = load_sid2qid(cfg)
    info(f"{len(sid2qid)} question→id rows for disclosure {cfg.disc}")
    quant, abstain_param, st = load_quant_questions(cfg)
    info(f"template {cfg.template}: {st['total']} question nodes; {st['datapoint']} carry XBRL datapoints")
    info(f"breakdown — quantitative: {st['quant']} | qualitative: {st['qual']} | parameter-numeric (skipped): {st['param']}")
    info(f"==> processing {len(quant)} QUANTITATIVE metric questions; {st['param']} parameter-numeric routed to review")

    step(f"Embed positions with {cfg.emb_dep}")
    posv = position_vectors(cfg, pos)
    pn = {k: _norm(v) for k, v in posv.items()}
    pids = list(pn)

    step(f"Embed the {len(set(humanize(c) for q in quant for c in q['concepts']))} numeric XBRL concept names")
    cvec = concept_vectors(cfg, [humanize(c) for q in quant for c in q["concepts"]])
    cn = {k: _norm(v) for k, v in cvec.items()}
    info(f"{len(cvec)} unique concepts embedded")

    parent_path = lambda pid: "/".join([x for x in pos["path"].get(pid, "").split("/") if x][:-1])
    sibs = defaultdict(set)
    for p in pos["path"]: sibs[parent_path(p)].add(p)
    def topk(vec, k): return sorted(((p, _dot(vec, pn[p])) for p in pids), key=lambda x: -x[1])[:k]
    def lineage(pid):
        segs = [int(x) for x in pos["path"].get(pid, "").split("/") if x]
        return " > ".join(pos["name"].get(s, "") for s in segs[:-1] if pos["name"].get(s, ""))

    step("Match concepts→positions, expand variant siblings, apply the confidence gate")
    confident, lowconf = [], []
    for q in quant:
        cand = {}
        for c in q["concepts"]:
            for p, s in topk(cn[humanize(c)], cfg.topk):
                cand[p] = max(cand.get(p, 0), s)
                for sp in sibs.get(parent_path(p), {p}):
                    cand.setdefault(sp, _dot(cn[humanize(c)], pn[sp]))
        ranked = sorted(cand.items(), key=lambda x: -x[1])
        top1 = ranked[0][1] if ranked else 0.0
        rec = {"nodeId": q["nodeId"], "dq_id": sid2qid.get(q["nodeId"]), "ref": q["ref"],
               "desc": q["desc"], "concepts": [humanize(c) for c in q["concepts"]],
               "top_score": round(top1, 3), "ranked": ranked}
        (confident if top1 >= cfg.conf else lowconf).append(rec)
    info(f"confident (top-1 ≥ {cfg.conf}): {len(confident)} | low-confidence → review: {len(lowconf)}")

    finalized = []
    if cfg.use_judge and confident:
        step(f"LLM judge ({cfg.chat_dep}, temp={cfg.temperature}): finalize the exact position(s) for {len(confident)} confident questions")
        cache_path = cfg.p("judge_cache.json")
        jcache = json.load(open(cache_path)) if (cfg.judge_cache and os.path.exists(cache_path)) else {}
        info(f"judge-verdict cache: {'ON' if cfg.judge_cache else 'OFF'}"
             + (f" ({len(jcache)} entries loaded)" if cfg.judge_cache else ""))
        n_cached = n_fresh = 0
        def jkey(r, pool):
            # Key on stable QUESTION identity (not the embedding-volatile pool) so reruns are 100%% cache hits.
            # Cached selections are still filtered to the live pool below, so a changed pool can't inject stale ids.
            payload = json.dumps({"m": cfg.chat_dep, "t": cfg.temperature, "node": r["nodeId"],
                                  "concepts": r["concepts"], "desc": r["desc"]}, sort_keys=True)
            return hashlib.sha256(payload.encode()).hexdigest()
        cli = _client()
        SYS = (f"You are an ESG reporting expert finalizing which internal metrics ('positions') answer a "
               f"QUANTITATIVE {cfg.fw_code} datapoint. From the CANDIDATES, select ALL and ONLY the positions that together "
               "correctly capture the datapoint, INCLUDING necessary variants (e.g., Scope 2 -> both Location-based "
               "AND Market-based). Prefer specific measurable positions over broad headers. Only use candidate IDs. "
               "If none truly fits, return an empty list. Respond as JSON {\"selected\":[ids],\"reasoning\":\"...\"}.")
        for i, r in enumerate(confident, 1):
            pool = r["ranked"][:cfg.judge_pool]
            lines = [f"id={p} | {pos['name'].get(p,'')} | unit={pos['unit'].get(p,'-')} | path={lineage(p)} | sim={s:.2f}"
                     for p, s in pool]
            user = (f"{cfg.fw_code} QUESTION {r['ref']}\nDatapoint concept(s): {', '.join(r['concepts'])}\n"
                    f"Requirement: {r['desc']}\n\nCANDIDATES:\n" + "\n".join(lines) + "\n\nSelect the final position id(s).")
            poolids = {p for p, _ in pool}; sel, reasoning = [], ""
            key = jkey(r, pool); src = "fresh"
            if cfg.judge_cache and key in jcache:
                sel = [p for p in jcache[key]["selected_ids"] if p in poolids]
                reasoning = jcache[key].get("reasoning", ""); src = "cached"; n_cached += 1
            else:
                for attempt in range(4):
                    try:
                        resp = cli.chat.completions.create(model=cfg.chat_dep,
                            messages=[{"role": "system", "content": SYS}, {"role": "user", "content": user}],
                            temperature=cfg.temperature,
                            response_format={"type": "json_object"})
                        d = json.loads(resp.choices[0].message.content)
                        sel = [int(x) for x in d.get("selected", []) if int(x) in poolids]
                        reasoning = (d.get("reasoning", "") or "")[:300]; break
                    except Exception:
                        if attempt == 3: reasoning = "ERROR"
                        time.sleep(2 ** attempt)
                n_fresh += 1
                jcache[key] = {"selected_ids": sel, "reasoning": reasoning, "ref": r["ref"]}
            score_by_pid = dict(r["ranked"])
            finalized.append({"nodeId": r["nodeId"], "ref": r["ref"], "dq_id": r["dq_id"], "concepts": r["concepts"],
                              "selected": [{"position_id": p, "name": pos["name"].get(p, ""),
                                            "conf": round(score_by_pid.get(p, 0.0), 3)} for p in sel],
                              "reasoning": reasoning})
            sel2 = finalized[-1]["selected"]
            verdict = f"{len(sel2)} position(s)" if sel2 else "no fit (GAP)"
            info(f"[{i}/{len(confident)}] {_trunc(r['ref'],32):32} → {verdict:16} [{src}]")
        if cfg.judge_cache:
            json.dump(jcache, open(cache_path, "w"), indent=0)
            info(f"judge verdicts: {n_cached} cached, {n_fresh} fresh → cache saved ({len(jcache)} entries)")
    elif not cfg.use_judge:
        step("LLM judge: skipped (--no-judge) — table shows retrieval top-1")

    step("Write reports and render the full report table")
    write_reports(cfg, pos, quant, confident, lowconf, abstain_param, finalized)
    summary(quant, confident, lowconf, abstain_param, finalized, cfg)
    print_full_table(cfg, pos, confident, lowconf, abstain_param, finalized)
    mapping_stats(confident, lowconf, abstain_param, finalized)

# ----------------------------------------------------------------------------- output
def write_reports(cfg, pos, quant, confident, lowconf, abstain_param, finalized):
    # reporter-facing
    with open(cfg.report_file("suggestions"), "w", encoding="utf-8") as f:
        f.write(f"# {cfg.fw_code} (template {cfg.template}) — position suggestions (quantitative)\n\n")
        f.write(f"Confident only (top-1 >= {cfg.conf}; candidates < {cfg.floor} suppressed). "
                f"{len(confident)}/{len(quant)} confident.\n\n")
        for r in confident:
            kept = [(p, s) for p, s in r["ranked"] if s >= cfg.floor][:6]
            f.write(f"## {r['ref']}  (dq_id={r['dq_id']})\n- concept(s): {', '.join(r['concepts'])}\n")
            for p, s in kept:
                f.write(f"  - [{round(s,3)}] {p} — {pos['name'].get(p,'')}\n")
            f.write("\n")
    # curator review queue
    with open(cfg.report_file("review"), "w", encoding="utf-8") as f:
        f.write(f"# {cfg.fw_code} (template {cfg.template}) — review queue (abstentions / gaps)\n\n")
        f.write(f"## Parameter-numerics (config, not metrics): {len(abstain_param)}\n")
        for a in abstain_param: f.write(f"- {a['ref']} — {', '.join(a['param_concepts'])}\n")
        f.write(f"\n## Low-confidence — likely no matching position: {len(lowconf)}\n")
        for r in lowconf:
            near = [(p, round(s, 3)) for p, s in r["ranked"][:3]]
            f.write(f"- **{r['ref']}** (dq_id={r['dq_id']}) top={r['top_score']} concept: {', '.join(r['concepts'])[:70]}; nearest={near}\n")
        if finalized:
            ja = [r for r in finalized if not r["selected"]]
            f.write(f"\n## Judge-abstained (confident pool, judge found no fit): {len(ja)}\n")
            for r in ja: f.write(f"- {r['ref']} — {r['reasoning'][:120]}\n")
    # finalized mappings
    if finalized:
        json.dump(finalized, open(cfg.report_file("final", "json"), "w"), indent=1)
        with open(cfg.report_file("final"), "w", encoding="utf-8") as f:
            f.write(f"# {cfg.fw_code} (template {cfg.template}) — finalized mappings (judge: {cfg.chat_dep})\n\n")
            for r in finalized:
                if not r["selected"]: continue
                f.write(f"## {r['ref']}  (dq_id={r['dq_id']})\n- concept(s): {', '.join(r['concepts'])}\n")
                for s in r["selected"]: f.write(f"  - {s['position_id']} — {s['name']}\n")
                f.write(f"  > {r['reasoning']}\n\n")

def _trunc(s, n): s = str(s); return s if len(s) <= n else s[:n - 1] + "…"

def _ascii_table(headers, rows):
    cols = len(headers)
    w = [len(h) for h in headers]
    for r in rows:
        for i in range(cols): w[i] = max(w[i], len(str(r[i])))
    sep = "+" + "+".join("-" * (x + 2) for x in w) + "+"
    line = lambda r: "| " + " | ".join(str(r[i]).ljust(w[i]) for i in range(cols)) + " |"
    return "\n".join([sep, line(headers), sep] + [line(r) for r in rows] + [sep])

def print_full_table(cfg, pos, confident, lowconf, abstain_param, finalized):
    score_by_node = {r["nodeId"]: dict(r["ranked"]) for r in confident}
    fin_by_node = {r["nodeId"]: r for r in finalized}
    rows = []
    for r in confident:
        node, q, dq = r["nodeId"], _trunc(r["ref"], 30), r["dq_id"] or ""
        fr = fin_by_node.get(node)
        if fr and fr["selected"]:
            first = True
            for s in fr["selected"]:
                rows.append(["MAPPED" if first else "", q if first else "", dq if first else "",
                             f"{s['position_id']} {_trunc(pos['name'].get(s['position_id'], ''), 40)}",
                             f"{s['conf']:.2f}"])
                first = False
        elif fr:  # confident pool but judge found no fit
            top = r["ranked"][0] if r["ranked"] else (None, 0)
            rows.append(["GAP", q, dq, f"no position fits · nearest {top[0]}", f"{top[1]:.2f}"])
        else:     # --no-judge: show retrieval top-1
            top = r["ranked"][0]
            rows.append(["CONFIDENT", q, dq, f"{top[0]} {_trunc(pos['name'].get(top[0], ''), 40)}", f"{top[1]:.2f}"])
    for r in lowconf:
        top = r["ranked"][0] if r["ranked"] else (None, 0)
        rows.append(["REVIEW", _trunc(r["ref"], 30), r["dq_id"] or "",
                     f"too weak · nearest {top[0]} {_trunc(pos['name'].get(top[0], ''), 22)}", f"{top[1]:.2f}"])
    for a in abstain_param:
        rows.append(["SKIP", _trunc(a["ref"], 30), "", "reporting parameter, not a metric", ""])
    print("\n" + "-" * 78)
    print("WHAT 'CONF' MEANS HERE (please read before judging the numbers)")
    print("-" * 78)
    print("  The CONF column is a TEXT-SIMILARITY score (0.00-1.00), NOT an AI/LLM")
    print("  'how-sure-am-I' confidence. It simply measures how closely the wording of")
    print("  the regulatory data point matches the wording of an internal metric.")
    print(f"    • {cfg.conf:.2f}+  = strong wording overlap — worth a real look")
    print(f"    • {cfg.floor:.2f}-{cfg.conf:.2f} = partial overlap — shown but weaker")
    print(f"    • below {cfg.floor:.2f} = too little overlap — set aside as REVIEW")
    print("  So 0.55 is a HEALTHY match for this kind of score — do not read it like an")
    print("  LLM probability where 0.55 would mean 'barely a coin-flip'. The actual")
    print("  yes/no decision is made by the AI judge afterward, not by this number.")
    print("-" * 78)
    print("\nFULL REPORT  (every processed question, with status)")
    print(_ascii_table(["STATUS", "QUESTION", "DQ_ID", "ANSWER POSITION", "CONF"], rows))
    print("  STATUS: MAPPED = position(s) found · GAP = numeric metric but no position exists · "
          "REVIEW = match too weak · SKIP = reporting parameter")

def mapping_stats(confident, lowconf, abstain_param, finalized):
    """How many questions got mapped to position(s) vs not."""
    mapped = sum(1 for r in finalized if r["selected"])
    total = len(confident) + len(lowconf) + len(abstain_param)
    print("\n" + "=" * 60)
    print(f"QUESTION MAPPING STATISTICS  (total: {total})")
    print(f"  mapped   : {mapped}")
    print(f"  unmapped : {total - mapped}")
    print("=" * 60)

def summary(quant, confident, lowconf, abstain_param, finalized, cfg):
    print("\n" + "=" * 60)
    print(f"{cfg.fw_code} template {cfg.template}  |  embed={cfg.emb_dep}  judge={cfg.chat_dep if cfg.use_judge else 'OFF'}")
    print(f"  quantitative metric questions : {len(quant)}")
    print(f"  confident (top-1 >= {cfg.conf})    : {len(confident)}")
    print(f"  abstain — low-confidence      : {len(lowconf)}")
    print(f"  abstain — parameter-numeric   : {len(abstain_param)}")
    if finalized:
        fin = [r for r in finalized if r["selected"]]
        print(f"  finalized by judge            : {len(fin)}")
        print(f"  judge-abstained               : {len(finalized) - len(fin)}")
    print(f"  reports -> {os.path.basename(cfg.report_file('suggestions'))}, "
          f"{os.path.basename(cfg.report_file('review'))}, {os.path.basename(cfg.report_file('final'))}")
    print("=" * 60)

# ----------------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description="Quantitative disclosure-question -> position mapping pipeline "
                                             "(ESRS by default; any framework via --framework)")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("run", "extract"):
        sp = sub.add_parser(name)
        sp.add_argument("--data"); sp.add_argument("--out")
        sp.add_argument("--framework", help="regulatory framework name/abbrev (e.g. ESRS, GRI, CDP, "
                                            "'EU Taxonomy', IFRS, 'SB 253'); resolves template+disclosure")
        sp.add_argument("--template", type=int, default=None,
                        help="disclosure_template_id (overrides --framework's pick; default 27 = ESRS 2026)")
        sp.add_argument("--disclosure", type=int, default=None,
                        help="disclosure_id (overrides --framework's pick; default 5 = ESRS 2026)")
        sp.add_argument("--conf", type=float, default=0.55)
        sp.add_argument("--floor", type=float, default=0.50)
        sp.add_argument("--no-judge", action="store_true")
        sp.add_argument("--no-judge-cache", action="store_true", help="ignore cached judge verdicts and re-query the LLM")
        sp.add_argument("--refresh-data", action="store_true")
        sp.add_argument("--refresh-embeddings", action="store_true")
        sp.add_argument("--ssh-host", default="sofi")
    a = ap.parse_args()
    if not a.cmd: ap.print_help(); return
    cfg = Cfg(a)
    if a.framework:
        fid, fname, tmpl, disc, year, nq = resolve_framework(cfg, a.framework)
        cfg.fw_id, cfg.fw_name = fid, fname
        cfg.fw_code = framework_code(fname)
        cfg.template = a.template if a.template is not None else tmpl
        cfg.disc     = a.disclosure if a.disclosure is not None else disc
        print(f"[framework] '{a.framework}' → {fname} (id {fid}) | "
              f"template {cfg.template}, disclosure {cfg.disc} (year {year}, {nq} questions)")
        if "esrs" not in fname.lower():
            print("[framework] NOTE: the quantitative mapper is tuned to ESRS XBRL datapoints; "
                  "non-ESRS frameworks may yield few/no quantitative matches.")
    else:
        cfg.template = a.template if a.template is not None else 27
        cfg.disc     = a.disclosure if a.disclosure is not None else 5
        cfg.fw_name  = "ESRS (European Sustainability Reporting Standards)"
    if a.cmd == "extract": cfg.refresh_data = True; extract_data(cfg)
    elif a.cmd == "run": run(cfg)

if __name__ == "__main__":
    main()
