# Architectural Recommendations — LLM-Based Position Down-Selection

_Date: 2026-06-16_
_Status: Option C selected. First action: measure recall on the golden data._

## Background

The goal is to suggest, for each disclosure question, the small set of internal **positions** an expert would map to it — matching the **golden data** in `sofi.disclosure_question_position` (~3,790 expert question→position links).

The existing implementation (separate codebase, per the Azure DevOps "Disclosure AI" wiki) uses a two-stage **bi-encoder embedding → cross-encoder reranking** pipeline. It is not reliably down-selecting candidates to match the expert selections.

## Constraints removed (decisions captured this session)

1. **Privacy constraint removed.** The wiki's "no external LLM / no customer data leaves the server" rule is no longer applicable. Hosted/capable LLMs are permitted. The LLM backend should remain swappable.
2. **Speed/latency constraint removed.** Throughput, cold-start, and the wiki's "reduce candidates 60→30 for speed" optimization no longer apply. **Accuracy is the sole objective.** Compute may be spent lavishly.

## The central insight: recall vs ranking

A two-stage funnel is **retrieve (cast a wide net) → rerank (order precisely)**. Two distinct failures:

- **Recall** — did the expert's correct position even make it onto the candidate shortlist? Measures *missing the right answer entirely*.
- **Ranking/precision** — given it's on the shortlist, is it near the top?

**The rerank stage's maximum achievable accuracy is hard-capped by the recall of the retrieve stage.** If retrieval drops the expert's position, no reranker — cross-encoder *or* LLM — can recover it. Therefore: swapping the cross-encoder for an LLM only helps if the failure is in *ranking*, not *retrieval*.

The success criteria from the wiki are effectively recall@K metrics (top-1 ≥60%, top-5 ≥75%, top-10 partial ≥90%, top-10 full set ≥50%).

**Consequence of removing the speed constraint:** recall stops being a hard problem. We can widen K arbitrarily and union multiple retrieval strategies (embeddings + keyword + hierarchy/lineage + framework-scoped) until the expert's positions are ≈always present. The difficulty then collapses onto **judgment** (down-selecting the right few from many) — exactly what an LLM with rich context does well and a cross-encoder does poorly.

---

## Option A — Wide-recall retrieval → single-pass LLM judge

Union several cheap retrievers into a generous pool (~100–300 candidates). Construct one comprehensive context (question + framework intent + each candidate's name, description, unit class, scope, lineage, siblings). The LLM down-selects with justifications in a single call (chunked if the pool exceeds the context window).

**Pros:** Simplest of the three; strong; mostly bounded by context-assembly quality; easy to evaluate; cheap relative to B/C.
**Cons:** Bounded by the wide-net recall; no ability for the model to investigate ambiguous cases beyond what's pre-assembled; single pass has no self-correction.

## Option B — Agentic LLM with database tools

No fixed candidate pool. Give the LLM tools — keyword/semantic search, position-lineage lookup, unit/scope filters, transaction-activity checks, fetch-full-position-detail — and let it *investigate*: issue queries, follow the hierarchy, gather evidence, and decide.

**Pros:** Highest ceiling; closest to "fully context-aware, makes intelligent choices"; can dig into ambiguous cases; not bounded by a fixed pre-filter.
**Cons:** Hardest to make consistent/deterministic; more LLM calls; harder to evaluate and debug; tool-use loops can wander without good guardrails.

## Option C — Hybrid + multi-pass consensus  ✅ SELECTED

Combine A and B: a deliberately **high-recall** wide net gives the LLM a near-complete field, *and* DB tools let it dig deeper on anything ambiguous. Then, since compute is now free, run **multiple independent passes** (or a generate → self-critique loop) and take **consensus**.

Attacks accuracy from every angle:
- **Recall** — via the wide net (the right answers are present).
- **Reasoning** — via tools + comprehensive context (units, scopes, hierarchy, framework intent).
- **Reliability** — via ensembling/self-critique (reduces single-pass variance and hallucination).

**Pros:** Best expected accuracy; resilient to both retrieval and ranking failure modes; self-correcting.
**Cons:** Most expensive and most complex by far — previously disqualifying, now acceptable because accuracy is the sole objective.

---

## Decision

**Proceed with Option C.**

## First action — measure recall on the golden data (before building)

Anchor the architecture on evidence, not intuition. Using `sofi.disclosure_question_position` as ground truth, measure **recall@K** of candidate retrieval:

- For each disclosure question with expert-mapped positions, determine whether the expert's position(s) appear within the retrieved top-K pool.
- This tells us where the real gap is:
  - **Low recall@K** → the problem is retrieval; the fix is a wider/smarter high-recall net (the front of Option C). An LLM reranker alone would not help.
  - **High recall@K but low top-10 accuracy** → the problem is ranking; the LLM-reasoning core of Option C is well-targeted.

This recall measurement sizes the wide net (how large K must be, which retrieval strategies to union) and validates the pivot before committing to the full Option C build.

## Reference

The local `smart-mapping` prototype in this repo already implements an early version of the LLM-reranker idea (heuristic candidate generation → LLM reranker fed a structured context with human workflow, tool definitions, few-shot examples, and candidate metadata). It maps `taxonomy_concept → position`, whereas the production target maps `disclosure_question → position/report`. Useful as a skeleton/reference for Option C.
