#!/usr/bin/env python3
"""
Smoke test for the triage LLM on a local Ollama server (stdlib only).

For each model it runs 12 labelled synthetic items through rubric.md and reports:
  - how often the reply is valid JSON (strict, or only after stripping fences/prose)
  - whether your pipeline's own parse_scores() accepts the reply (when run from the project root)
  - whether the fields and value ranges match the schema
  - seconds per item and tokens/s  ->  estimated minutes for a full run
  - whether scores behave: audio-core items beat non-audio items, marketing is scored low,
    open weights beat closed API

Usage:
  python triage_smoketest.py --models qwen3.5:9b qwen3:8b qwen2.5:7b-instruct   # run from the project root
  python triage_smoketest.py --models qwen3.5:9b --also-think     # compare thinking on
  python triage_smoketest.py --models qwen3.5:9b --no-schema      # plain format=json
"""
import argparse
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:   # use the pipeline's real parser/scoring when run from the project root
    from briefing.triage import parse_scores
except Exception:
    parse_scores = None

KINDS = {"new_architecture", "new_model", "finetune", "method", "framework",
         "benchmark", "dataset", "survey", "other"}
SCORE_KEYS = ("novelty", "evidence", "openness", "relevance")

SCHEMA = {
    "type": "object",
    "properties": {
        "novelty": {"type": "integer", "minimum": 0, "maximum": 10},
        "evidence": {"type": "integer", "minimum": 0, "maximum": 10},
        "openness": {"type": "integer", "minimum": 0, "maximum": 10},
        "relevance": {"type": "integer", "minimum": 0, "maximum": 10},
        "kind": {"type": "string", "enum": sorted(KINDS)},
        "one_line": {"type": "string"},
    },
    "required": ["novelty", "evidence", "openness", "relevance", "kind", "one_line"],
}

# (id, group, title, text). All synthetic, written for this test; none is a real paper.
ITEMS = [
    ("H1", "core", "Cache-aware streaming FastConformer for low-latency ASR",
     "We present a streaming speech recognition model with a chunk-wise cache-aware encoder and a "
     "lookahead-limited decoder. On LibriSpeech test-other it reaches 3.4% WER at 320 ms latency, versus "
     "4.1% for a streaming Conformer-Transducer baseline and 3.9% for chunked Whisper-large-v3. Code and "
     "weights are released under Apache-2.0."),
    ("H2", "core", "Overlap-aware end-to-end diarisation with attractor refinement",
     "Our model reaches 11.8% DER on AMI and 13.5% on DIHARD III, compared with 13.9% and 15.7% for a "
     "pyannote 3.1 pipeline. Weights and inference code are released under the MIT licence."),
    ("H3", "core", "Large-margin training for speaker verification on short utterances",
     "Using a new margin schedule we obtain 0.61% EER on VoxCeleb1-O versus 0.89% for an ECAPA-TDNN "
     "baseline and 0.73% for CAM++. Code is available and checkpoints are released under CC-BY-NC 4.0."),
    ("H4", "core", "Enrolment-conditioned target speaker extraction in noisy mixtures",
     "Conditioned on a 3-second enrolment clip, our extractor reaches 14.2 dB SI-SDRi on noisy Libri2Mix "
     "versus 12.7 dB for SpEx+. Code is released; weights are available on request."),
    ("H5", "core", "A 4M-parameter causal speech enhancement model for real-time denoising",
     "On the DNS Challenge test set we obtain DNSMOS OVRL 3.35 versus 3.21 for DeepFilterNet3, at 0.05 "
     "real-time factor on a laptop CPU. Weights and code are released under MIT."),
    ("H6", "core", "An open speech LLM for transcription and spoken question answering",
     "Our 7B audio language model averages 6.1 WER over the Open ASR Leaderboard datasets versus 6.5 for "
     "Whisper-large-v3, and also answers spoken questions. Weights are released under Apache-2.0."),
    ("H7", "core", "Spoken language identification for 120 languages from frozen self-supervised features",
     "On FLEURS we reach 96.2% language identification accuracy versus 93.1% for Whisper's built-in "
     "language detection. Code is released."),
    ("L1", "offtopic", "Few-step text-to-image generation with consistency distillation",
     "We distil a diffusion model into a 2-step generator, reaching FID 5.1 on COCO. Code is released."),
    ("L2", "offtopic", "Reinforcement learning for long-horizon mathematical reasoning",
     "A new RL recipe lifts a 7B language model from 61% to 72% on MATH500. Weights are released."),
    ("L3", "offtopic", "Zero-shot voice cloning TTS with flow matching",
     "Our text-to-speech model clones a voice from 3 seconds of audio, reaching speaker similarity 0.67 "
     "and MOS 4.2. Weights and code are released under Apache-2.0."),
    ("L4", "offtopic", "Camera-controllable video generation with 3D-aware diffusion",
     "We add explicit camera control to a video diffusion model and improve FVD on RealEstate10K."),
    ("M1", "marketing", "Introducing AuraVoice: the most accurate speech recognition ever",
     "Our new proprietary API delivers state-of-the-art accuracy across all languages and accents. "
     "Contact sales for pricing."),
]


def post(url, payload, timeout):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def call(base, model, system, user, think, use_schema, timeout):
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": SCHEMA if use_schema else "json",
        "options": {"temperature": 0, "num_ctx": 4096},
    }
    note = ""
    if think is not None:
        payload["think"] = think
    t0 = time.time()
    try:
        data = post(base + "/api/chat", payload, timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if e.code == 400 and "think" in body.lower() and "think" in payload:
            del payload["think"]            # model has no thinking mode: retry without the flag
            note = "think-flag-unsupported"
            t0 = time.time()
            data = post(base + "/api/chat", payload, timeout)
        else:
            raise RuntimeError(f"HTTP {e.code}: {body[:200]}")
    wall = time.time() - t0
    msg = data.get("message", {})
    return {
        "content": msg.get("content", ""),
        "thinking": msg.get("thinking", "") or "",
        "wall": wall,
        "out_tokens": data.get("eval_count", 0),
        "tok_s": (data["eval_count"] / (data["eval_duration"] / 1e9))
                 if data.get("eval_count") and data.get("eval_duration") else 0.0,
        "note": note,
    }


def extract_json(text):
    """Returns (obj, how). how: 'strict' | 'repaired' | None."""
    try:
        return json.loads(text), "strict"
    except Exception:
        pass
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return json.loads(stripped), "repaired"
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, flags=re.S)       # first '{' to last '}'
    if m:
        try:
            return json.loads(m.group(0)), "repaired"
        except Exception:
            pass
    return None, None


def schema_problems(obj):
    if not isinstance(obj, dict):
        return ["not an object"]
    bad = []
    for k in SCORE_KEYS:
        v = obj.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 10:
            bad.append(f"{k}={v!r}")
    if obj.get("kind") not in KINDS:
        bad.append(f"kind={obj.get('kind')!r}")
    ol = obj.get("one_line")
    if not isinstance(ol, str) or not ol.strip():
        bad.append("one_line missing")
    elif len(ol.split()) > 30:
        bad.append("one_line too long")
    return bad


def run_model(args, system, model, think):
    label = f"{model} | think={'default' if think is None else think}"
    print(f"\n=== {label}")
    try:   # warm-up so model load time is not counted
        call(args.url, model, system, "TITLE: warm-up\nTEXT: hello", think, not args.no_schema, args.timeout)
    except Exception as e:
        print(f"  could not run this model: {e}")
        return None
    rows = []
    for item_id, group, title, text in ITEMS:
        user = f"TITLE: {title}\nTEXT: {text}"
        try:
            r = call(args.url, model, system, user, think, not args.no_schema, args.timeout)
        except Exception as e:
            print(f"  {item_id}: request failed: {e}")
            rows.append({"id": item_id, "group": group, "how": None, "problems": ["request failed"], "wall": 0,
                         "out_tokens": 0, "tok_s": 0, "thinking": "", "obj": None, "note": "",
                         "ptotal": None, "perr": "request failed"})
            continue
        obj, how = extract_json(r["content"])
        problems = schema_problems(obj) if obj is not None else ["no JSON"]
        ptotal = perr = None
        if parse_scores:
            try:
                ptotal = parse_scores(r["content"])["total"]
            except Exception as e:
                perr = str(e)[:80]
        rows.append({"id": item_id, "group": group, "how": how, "problems": problems, "obj": obj,
                     "ptotal": ptotal, "perr": perr, **r})
        if args.verbose and (how != "strict" or problems):
            print(f"  {item_id}: how={how} problems={problems}\n    raw: {r['content'][:300]!r}")
        elif args.verbose:
            o = obj
            print(f"  {item_id}: N{o['novelty']} E{o['evidence']} O{o['openness']} R{o['relevance']} {o['kind']}")
    return rows


def summarise(label, rows, n_est):
    n = len(rows)
    strict = sum(r["how"] == "strict" for r in rows)
    usable = sum(r["how"] is not None and not r["problems"] for r in rows)
    walls = [r["wall"] for r in rows if r["wall"]]
    toks = [r["out_tokens"] for r in rows if r["out_tokens"]]
    tps = [r["tok_s"] for r in rows if r["tok_s"]]
    thinking = sum(bool(r["thinking"]) for r in rows)
    sec = statistics.mean(walls) if walls else float("nan")

    def rel(group):
        v = [r["obj"]["relevance"] for r in rows if r["group"] == group and r["obj"] and not r["problems"]]
        return statistics.mean(v) if v else float("nan")

    by_id = {r["id"]: r["obj"] for r in rows if r["obj"] and not r["problems"]}
    sep = rel("core") - rel("offtopic")
    m1, h1 = by_id.get("M1"), by_id.get("H1")
    totals = {r["id"]: r["ptotal"] for r in rows if r["ptotal"] is not None}
    parser_ok = len(totals)
    checks = {
        "core audio items score >=4 higher relevance than off-topic": sep >= 4,
        "marketing item: novelty, evidence, openness all <=3":
            bool(m1) and all(m1[k] <= 3 for k in ("novelty", "evidence", "openness")),
        "open Apache-2.0 ASR (H1) openness >=8 and above closed API (M1)":
            bool(h1 and m1) and h1["openness"] >= 8 and h1["openness"] > m1["openness"],
    }
    if parse_scores:
        core = [totals[i] for i, g, *_ in ITEMS if g == "core" and i in totals]
        off = [totals[i] for i, g, *_ in ITEMS if g == "offtopic" and i in totals]
        checks["your parse_scores totals: every core item outranks every off-topic item"] = (
            bool(core and off) and min(core) > max(off))
        checks["your parse_scores totals: marketing (M1) ranks below every core item"] = (
            "M1" in totals and bool(core) and totals["M1"] < min(core))
    print(f"\n--- {label}")
    print(f"  valid JSON, strict:            {strict}/{n}")
    if parse_scores:
        print(f"  accepted by your parse_scores: {parser_ok}/{n}")
        for r in rows:
            if r["perr"]:
                print(f"    {r['id']} rejected: {r['perr']}")
    else:
        print("  (run from the project root to also test your real parse_scores)")
    print(f"  usable (JSON + schema ok):     {usable}/{n}")
    print(f"  seconds/item (mean):           {sec:.1f}")
    print(f"  output tokens/item (mean):     {statistics.mean(toks) if toks else 0:.0f}")
    print(f"  generation speed (tok/s):      {statistics.mean(tps) if tps else 0:.1f}")
    print(f"  items that returned thinking:  {thinking}/{n}"
          + ("   <- thinking is on: slow, and may hurt JSON" if thinking else ""))
    print(f"  mean relevance core/off-topic: {rel('core'):.1f} / {rel('offtopic'):.1f}")
    print(f"  est. time for {n_est} items:        {sec * n_est / 60:.0f} min")
    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    notes = {r["note"] for r in rows if r["note"]}
    if notes:
        print(f"  notes: {', '.join(sorted(notes))}")
    # your parser tolerates fences and prose, so it decides when available; strictness only matters without it
    accepted = parser_ok == n if parse_scores else (usable == n and strict >= n - 1)
    verdict = accepted and usable >= n - 1 and all(checks.values()) and thinking == 0
    print(f"  => {'GOOD triage candidate' if verdict else 'needs a look (see FAIL lines / run with --verbose)'}")
    return verdict


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--url", default="http://localhost:11434")
    ap.add_argument("--prompt", default=str(Path(__file__).with_name("rubric.md")))
    ap.add_argument("--also-think", action="store_true", help="also try each model with think=True")
    ap.add_argument("--no-schema", action="store_true", help='use format="json" instead of a JSON schema')
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--est-items", type=int, default=200, help="items per real run, for the time estimate")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    system = Path(args.prompt).read_text()
    results = []
    for model in args.models:
        modes = [False] + ([True] if args.also_think else [])
        for think in modes:
            rows = run_model(args, system, model, think)
            if rows:
                results.append((f"{model} | think={think}", summarise(f"{model} | think={think}", rows, args.est_items)))
    print("\n=== OVERVIEW")
    for label, ok in results:
        print(f"  {'GOOD ' if ok else 'check'}  {label}")
    return 0 if any(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())