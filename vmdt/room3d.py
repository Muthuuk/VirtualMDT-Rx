"""The 3D consulting room.

Draws each convened expert as a small 3D figure standing in a curved row, using
only HTML and CSS 3D transforms (no plug-ins, no JavaScript, no outside files),
so it works the same in Colab, on Hugging Face and offline.

Each figure shows: a coloured ring for its verdict (green / amber / red), whether
its human counterpart can be reached right now, and its headline finding. Hover
over, tap or tab to a figure to turn its card round and read the details.

These figures are software experts, not real people and not video avatars.
"""
from __future__ import annotations

from html import escape
from typing import List

from .models import AMBER, INFO, RED, CaseResult

RING = {RED: "#E5484D", AMBER: "#F5A524", INFO: "#30A46C", "OFF": "#8B95A1"}
WORD = {RED: "Stop", AMBER: "Caution", INFO: "No concern"}

CSS = """
<style>
.vmdt-room{background:radial-gradient(ellipse at 50% 0%,#24344d 0%,#141c2b 70%);border-radius:18px;padding:22px 14px 30px;
  perspective:1400px;overflow:hidden;font-family:inherit;color:#EEF2F7}
.vmdt-room .ttl{margin:0 0 4px 8px;font-size:1.3rem;color:#fff !important;font-weight:700}
.vmdt-room .sub{margin:0 0 16px 8px;font-size:1.02rem;color:#C9D3DF !important}
.vmdt-row{display:flex;flex-wrap:wrap;justify-content:center;gap:16px 14px;transform-style:preserve-3d}
.vx{width:178px;height:322px;position:relative;transform-style:preserve-3d;outline:none;cursor:pointer}
.vx::before{content:'';position:absolute;inset:0;background:rgba(0,0,0,.001);border-radius:16px}
.vx .turn{position:absolute;inset:0;transform-style:preserve-3d;transition:transform .7s cubic-bezier(.2,.7,.2,1)}
.vx:hover .turn,.vx:focus .turn,.vx:focus-within .turn{transform:rotateY(180deg)}
.vx .face{position:absolute;inset:0;backface-visibility:hidden;-webkit-backface-visibility:hidden;border-radius:16px;
  background:linear-gradient(180deg,rgba(255,255,255,.10),rgba(255,255,255,.03));border:1px solid rgba(255,255,255,.16);
  box-shadow:0 18px 30px rgba(0,0,0,.35);padding:12px 10px;text-align:center}
.vx .back{transform:rotateY(180deg);text-align:left;overflow-y:auto;overflow-x:hidden;word-break:break-word;background:linear-gradient(180deg,#22304a,#18233a)}
.vx .back b{font-size:1.02rem;color:#fff}
.vx .back p{font-size:.95rem;line-height:1.35;margin:6px 0;color:#DCE4EE}
.vx .back .src{font-size:.82rem;color:#9FB0C4}
.fig{height:128px;position:relative;margin:2px auto 6px;width:120px;transform-style:preserve-3d;animation:vbob 4.2s ease-in-out infinite}
.fig .ring{position:absolute;left:50%;bottom:0;width:112px;height:30px;margin-left:-56px;border-radius:50%;
  transform:rotateX(68deg);border:5px solid var(--ring);box-shadow:0 0 22px var(--ring),inset 0 0 14px var(--ring)}
.fig .body{position:absolute;left:50%;bottom:14px;width:78px;height:66px;margin-left:-39px;border-radius:38px 38px 16px 16px;
  background:radial-gradient(circle at 32% 22%,rgba(255,255,255,.55),transparent 42%),linear-gradient(160deg,var(--coat),#10151f 130%);
  box-shadow:inset -10px -8px 16px rgba(0,0,0,.35)}
.fig .head{position:absolute;left:50%;bottom:74px;width:52px;height:52px;margin-left:-26px;border-radius:50%;
  background:radial-gradient(circle at 34% 30%,#fff 0%,#f1d9c4 26%,#c99b7c 70%,#8d6a55 100%);box-shadow:inset -6px -6px 10px rgba(0,0,0,.28)}
.fig .badge{position:absolute;left:50%;bottom:34px;margin-left:-13px;width:26px;height:26px;border-radius:7px;background:#fff;
  color:var(--coat);font-weight:800;font-size:.95rem;line-height:26px;transform:translateZ(18px)}
.vx.red .ring{animation:vpulse 1.1s ease-in-out infinite}
.vx .nm{font-size:1.08rem;font-weight:700;color:#fff;margin-top:2px}
.vx .rl{font-size:.88rem;color:#B9C4D3;min-height:2.3em;line-height:1.15}
.vx .verdict{display:inline-block;margin:6px 0 4px;padding:3px 12px;border-radius:999px;font-size:.98rem;font-weight:700;
  background:var(--ring);color:#101418}
.vx .avail{font-size:.84rem;line-height:1.2;color:#C9D3DF}
.vx .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;background:var(--dot)}
.vx .ms{font-size:.8rem;color:#93A2B5;margin-top:3px}
.vmdt-legend{margin:16px 8px 0;font-size:.95rem;color:#C9D3DF !important}
.vmdt-legend span{display:inline-block;margin-right:16px;color:#C9D3DF !important}
@keyframes vbob{0%,100%{transform:translateY(0) rotateY(-8deg)}50%{transform:translateY(-7px) rotateY(8deg)}}
@keyframes vpulse{0%,100%{box-shadow:0 0 14px var(--ring),inset 0 0 10px var(--ring)}50%{box-shadow:0 0 38px var(--ring),inset 0 0 22px var(--ring)}}
@media (prefers-reduced-motion:reduce){.fig,.vx.red .ring{animation:none}.vx .turn{transition:none}}
</style>
"""


def empty_room() -> str:
    return CSS + ('<div class="vmdt-room"><div class="ttl">The virtual MDT room</div>'
                  '<p class="sub">Enter a request and press "Convene the virtual team". The experts this case needs will appear here.</p></div>')


def render(result: CaseResult, when_label: str = "") -> str:
    by_agent = {r.agent: r for r in result.reports}
    n = len(result.convened)
    cards: List[str] = []
    for i, c in enumerate(result.convened):
        rep = by_agent.get(c["agent"])
        level = rep.worst if rep else INFO
        notable = [f for f in (rep.findings if rep else []) if f.level != INFO] or (rep.findings if rep else [])
        head = notable[0] if notable else None
        angle = (i - (n - 1) / 2) * (34 / max(n - 1, 1))  # curve the row gently towards the viewer
        if c["human"] is None:
            dot, avail = RING["OFF"], "Reference expert"
        else:
            dot, avail = (RING[INFO] if c["available"] else RING["OFF"]), escape(c["note"])
        back = "".join(f"<p><b>{escape(f.title)}</b><br>{escape(f.detail)}<br><span class='src'>{escape(f.code)} · {escape(f.source)}</span></p>"
                       for f in notable[:3]) or "<p>Nothing to report for this request.</p>"
        cards.append(f"""
<div class="vx {'red' if level == RED else ''}" tabindex="0" style="--ring:{RING[level]};--coat:{c['colour']};--dot:{dot};
     transform:rotateY({-angle:.1f}deg) translateZ({(17 - abs(angle)) * 2.2:.0f}px)" aria-label="{escape(c['name'])}: {WORD[level]}">
 <div class="turn">
  <div class="face">
   <div class="fig"><div class="ring"></div><div class="body"></div><div class="head"></div><div class="badge">{escape(c['name'][0])}</div></div>
   <div class="nm">{escape(c['name'])}</div><div class="rl">{escape(c['role'])}</div>
   <div class="verdict">{WORD[level]}</div>
   <div class="avail"><span class="dot"></span>{avail}</div>
   <div class="ms">{'core team' if c['core'] else 'called in'} · {rep.ms if rep else 0:.0f} ms</div>
  </div>
  <div class="face back"><b>{escape(c['name'])}</b>{back}</div>
 </div>
</div>""")
    core = sum(1 for c in result.convened if c["core"])
    sub = f"{n} experts reviewed this request at the same time: {core} core and {n - core} called in. Finished in {result.total_ms:.0f} ms."
    if result.sequential_ms > 2 * result.total_ms:  # only worth saying when experts take real time (web look-ups or the demo delay)
        sub += f" One after another would have taken {result.sequential_ms:.0f} ms."
    if when_label:
        sub += f" Availability shown for {escape(when_label)}."
    return (CSS + f'<div class="vmdt-room"><div class="ttl">The virtual MDT room</div><p class="sub">{sub}</p>'
            f'<div class="vmdt-row">{"".join(cards)}</div>'
            '<div class="vmdt-legend"><span>Ring colour = verdict</span><span><i class="dot" style="display:inline-block;width:10px;height:10px;'
            f'border-radius:50%;background:{RING[INFO]}"></i> human counterpart reachable now</span>'
            '<span>Hover, tap or tab to a figure to turn the card and read its reasons</span></div></div>')
