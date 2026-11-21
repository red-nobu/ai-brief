# AI Briefing

Daily email on new multimodal AI work (audio/speech, image, video, translation) from papers, Hugging Face,
GitHub, ModelScope and lab blogs, judged on content rather than brand. Built to run on an Apple Silicon Mac.

## How it works
```
collectors: arXiv | HF models + daily papers | GitHub | ModelScope | RSS (labs/blogs)
  -> Store (SQLite) dedupe: only new items          [briefing/store.py]
  -> pre-filter: keyword interests + per-source cap [briefing/filter.py]
  -> triage: local LLM scores novelty/evidence/openness/relevance with rubric.md,
             org/stars/likes are HIDDEN from the model [briefing/triage.py]
  -> select: long-tail slots filled first, then big-lab slots [briefing/write.py]
  -> deep read of the top items: method, claims, numbers, caveats [briefing/deepread.py]
  -> write brief (+ per-item confidence tag) -> email [briefing/send.py]
```
Each LLM stage is set in `config.yaml` (`ollama | gemini | groq | anthropic`). A failing source, feed or
single LLM reply is logged and skipped; it never stops the run.

## Setup on the Mac
1. Copy this folder over, `cd` into it.
2. `./scripts/setup_mac.sh`   (Homebrew: uv + Ollama; pulls `qwen2.5:7b-instruct`; runs tests)
3. Edit `.env`: Gmail address + **app password** (needs 2-step verification; myaccount.google.com/apppasswords),
   `MAIL_TO`, and a free `GEMINI_API_KEY` or `GROQ_API_KEY`.
   No API key at all? In `config.yaml` set the `write:` stage to `provider: ollama` too.
4. `uv run python main.py --check`            # tests email login, each LLM, each source; tells you what to fix
5. `uv run python main.py --dry-run --no-llm` # data only, no LLM
   `uv run python main.py --dry-run`          # full pipeline, prints the brief, sends nothing
   `uv run python main.py`                    # sends the email and marks items as seen
6. `./scripts/install_launchd.sh 8 0`         # daily 08:00. Test: `launchctl kickstart gui/$(id -u)/com.user.aibriefing`
7. Monthly: `uv run python main.py --audit`   # share of big labs vs long tail, by source, kind, org

## Customising
- `config.yaml`: interests, RSS feeds (add small labs / university groups), GitHub queries, slots, model names,
  `big_orgs`. `rubric.md`: how items are scored. Models by RAM: 7B for 16 GB; try 14B on 32 GB+.

## Troubleshooting (start with `--check`)
| Symptom | Fix |
|---|---|
| SMTP login fails | Use a Gmail *app password*, not your account password; port 465 |
| `Ollama not reachable` | `ollama serve` (the launchd script starts it if it is down) |
| `model not pulled` | `ollama pull qwen2.5:7b-instruct` or change `llm.triage.model` |
| 429 / quota from Gemini/Groq | free-tier limit; lower `triage.deep_read_top`, or set `write:` to ollama |
| `triage produced nothing` | the triage LLM is failing; run `--check`, look at `logs/daily.log` |
| GitHub returns 0 items | unauthenticated search is limited to ~10 req/min; set `GITHUB_TOKEN` |
| Brief is empty / "No new relevant items" | normal on quiet days; items already briefed are not repeated |
| Nothing arrives at 08:00 | Mac was asleep (runs on wake) or check `logs/launchd.err` and `logs/daily.log` |

## Status and known gaps
Verified here: all collectors against the live sources, dedupe, pre-filter, slot allocation, the full LLM
pipeline against a **stub** Ollama server, email message construction with a mocked SMTP server, 13 unit tests.

**Not verified on real services** (no credentials or Ollama where this was built): real SMTP delivery,
real Ollama / Gemini / Groq replies. Use `--check` first. Small local models may return malformed JSON for
some items; those items are skipped and logged, so if many are skipped, try a bigger model.

Known limitations:
- arXiv gives no author affiliations, so every arXiv paper counts as long-tail; big-lab detection works on
  HF org, GitHub owner, ModelScope namespace and RSS feed name only.
- Triage reads abstracts/READMEs/model cards, not full PDFs; "evidence" scores are only as good as the text.
- Keyword pre-filter can miss unusual wording (edit `interests`). Embedding similarity is not implemented.
- Not built: automatic watchlist discovery of new labs, weekly trends roundup, ranking by author history.
- Free-tier API terms and limits change; check them.
