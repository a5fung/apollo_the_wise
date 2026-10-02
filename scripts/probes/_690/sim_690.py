"""#690 DoD — a SIMULATED release through the pre-adoption replay. PRACTICE ONLY:
no write_cache, no role hold recorded, no adoption audit row. Spend is real and logged
(caller=model_replay). One Telegram: the real digest renderer, with a practice header
and footer in place of the adoption footer."""
import asyncio, json, time
from shared import llm_models
from agents.market_intelligence import model_resolution as mr

TIER = "sonnet"
CANDIDATES = ["claude-sonnet-5", "claude-opus-5-5"]

async def main():
    current = llm_models.effective_model("THEME_MODEL")
    ids = await mr._list_model_ids()
    new_id = next((c for c in CANDIDATES if c in ids and c != current), None)
    print("current", current, "| served candidates", [c for c in CANDIDATES if c in ids], "| forced new id", new_id)
    if not new_id:
        print("NO CANDIDATE SERVED — abort"); return
    ok, err = await mr._canary_model(new_id)
    print("canary", ok, err)
    if not ok:
        print("canary rejected — the real path would refuse the release here; abort"); return
    roles = {r for r, t in llm_models.RESOLVED_ROLES.items() if t == TIER}
    entries, skips = mr._replay_inventory(roles, current)
    print("entries", len(entries))
    t0 = time.monotonic()
    replays = await mr._replay_entries(entries, new_id, time.monotonic() + 900)
    print(f"replayed in {time.monotonic()-t0:.0f}s")
    if any(r.verdict == mr.BUDGET for kr in replays for r in kr.runs):
        print("BUDGET ran out — the real path would keep the tier and report it")
    would_hold = {}
    for role in sorted({kr.role for kr in replays}):
        runs = [r for kr in replays if kr.role == role for r in kr.runs]
        held = mr.role_is_held(runs)
        print(f"VERDICT {role:34} {'HOLD' if held else 'pass'}  runs={[r.verdict for r in runs]}")
        if held:
            would_hold[role] = {"model": current, "error": mr._first_failure(runs)[:300], "candidate": new_id}
    for kr in replays:
        print(f"  KEY {kr.key[-60:]:60} {[ (r.verdict, (r.error or '')[:90]) for r in kr.runs]}")
    print("DETAIL", mr._digest_detail(TIER, current, new_id, replays, would_hold))
    text = mr._render_tier_digest(TIER, current, new_id, current, replays, skips, would_hold, {}, {})
    body = text.split("\nNothing changed yet")[0]
    header = ("🧪 <b>PRACTICE RUN (#690) — nothing was adopted or held; your models are unchanged.</b>\n"
              "A real release would send you this before switching:\n\n")
    footer = ("\n\nThis was a test of the new-model check, run on our own recent requests. "
              "No action needed.")
    msg = header + body + footer
    print("TELEGRAM\n" + msg)
    from agents.market_intelligence.briefing import send_telegram_message
    sent = await send_telegram_message(msg, parse_mode="HTML")
    print("TELEGRAM_SENT", sent)

asyncio.run(main())
