# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import automate_firewall_webui_crawl as base


DANGER_RE = re.compile(
    r"(?i)(usb|engineering|firmware|factory\s*reset|reboot|restart|backup|restore|logout)"
)
ROOT = Path(
    os.environ.setdefault(
        "NR2301_WEBUI_EVIDENCE_DIR",
        f"firewall_webui_autopilot_v2_{datetime.now():%Y%m%d-%H%M%S}",
    )
)
ROOT.mkdir(parents=True, exist_ok=True)
DISCOVERY: list[dict[str, object]] = []
STEP = 0
ORIGINAL_CLICK_BUTTON = base.click_button


def _body_text(page: Any) -> str:
    try:
        return page.locator("body").inner_text(timeout=3000)
    except Exception:
        return ""


def _clickables(page: Any) -> list[dict[str, str]]:
    try:
        return list(
            page.evaluate(
                """() => {
                  const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
                  const els=[...document.querySelectorAll('a,button,[role=button],[role=link],[role=menuitem],[role=tab],[onclick],div,span,li')];
                  const out=[];
                  for(const e of els){
                    if(!visible(e)) continue;
                    const text=((e.innerText||e.textContent||'').trim().replace(/\\s+/g,' '));
                    if(!text || text.length>160) continue;
                    const cs=getComputedStyle(e);
                    const interactive=['A','BUTTON'].includes(e.tagName)||e.hasAttribute('onclick')||['button','link','menuitem','tab'].includes(e.getAttribute('role'))||cs.cursor==='pointer';
                    if(!interactive) continue;
                    out.push({tag:e.tagName,text,role:e.getAttribute('role')||'',href:e.getAttribute('href')||'',id:e.id||'',class:e.className||''});
                    if(out.length>=250) break;
                  }
                  return out;
                }"""
            )
        )
    except Exception:
        return []


def dump_ui(page: Any, label: str) -> None:
    global STEP
    STEP += 1
    body = _body_text(page)
    clickables = _clickables(page)
    entry = {
        "step": STEP,
        "label": label,
        "url": page.url,
        "body_text": body,
        "clickables": clickables,
    }
    DISCOVERY.append(entry)
    (ROOT / "firewall_webui_v2_discovery.json").write_text(
        json.dumps(DISCOVERY, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (ROOT / f"firewall_webui_v2_{STEP:02d}_{label}.txt").write_text(
        body, encoding="utf-8"
    )
    try:
        page.screenshot(path=str(ROOT / f"firewall_webui_v2_{STEP:02d}_{label}.png"), full_page=True)
    except Exception:
        pass


def generic_click(page: Any, words: tuple[str, ...], *, exact_first: bool = True) -> str | None:
    words = tuple(w for w in words if w and not DANGER_RE.search(w))
    if not words:
        return None
    try:
        result = page.evaluate(
            """({words,exactFirst}) => {
              const bad=/(usb|engineering|firmware|factory\\s*reset|reboot|restart|backup|restore|logout)/i;
              const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
              const norm=s=>(s||'').trim().replace(/\\s+/g,' ');
              const lows=words.map(w=>w.toLowerCase());
              const nodes=[...document.querySelectorAll('a,button,[role=button],[role=link],[role=menuitem],[role=tab],[onclick],label,div,span,li,td,p')];
              function score(e){
                if(!visible(e)) return -1;
                const text=norm(e.innerText||e.textContent||'');
                if(!text || text.length>180 || bad.test(text)) return -1;
                const l=text.toLowerCase();
                let s=-1;
                for(let i=0;i<lows.length;i++){
                  const w=lows[i];
                  if(l===w) s=Math.max(s,1000-i);
                  else if(l.includes(w)) s=Math.max(s,500-i);
                }
                if(s<0) return -1;
                const cs=getComputedStyle(e);
                if(['A','BUTTON'].includes(e.tagName)||e.hasAttribute('onclick')||['button','link','menuitem','tab'].includes(e.getAttribute('role'))||cs.cursor==='pointer') s+=200;
                return s;
              }
              let ranked=nodes.map(e=>[score(e),e]).filter(x=>x[0]>=0).sort((a,b)=>b[0]-a[0]);
              if(!ranked.length) return null;
              let e=ranked[0][1];
              let click=e;
              for(let i=0;i<6 && click;i++){
                const cs=getComputedStyle(click);
                if(['A','BUTTON'].includes(click.tagName)||click.hasAttribute('onclick')||['button','link','menuitem','tab'].includes(click.getAttribute('role'))||cs.cursor==='pointer') break;
                click=click.parentElement;
              }
              click=click||e;
              const text=norm(e.innerText||e.textContent||'');
              click.click();
              return text;
            }""",
            {"words": list(words), "exactFirst": exact_first},
        )
    except Exception:
        return None
    if result:
        time.sleep(0.9)
        return str(result)
    return None


def click_button_v2(page: Any, words: tuple[str, ...]) -> bool:
    if ORIGINAL_CLICK_BUTTON(page, words):
        return True
    clicked = generic_click(page, words)
    if clicked:
        dump_ui(page, "clicked_" + re.sub(r"[^A-Za-z0-9]+", "_", clicked)[:40])
        return True
    return False


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(w.lower() in low for w in words)


def navigate_v2(page: Any, words: tuple[str, ...]) -> bool:
    joined = " ".join(words).lower()
    specific = tuple(
        w for w in words
        if w.lower() not in {"firewall", "wan", "nat", "security", "network setting", "sicherheit"}
    ) or words

    dump_ui(page, "navigate_start")

    # The real NR2301 dashboard exposes Firewall/NAT below APP MODULE.  The
    # element is not guaranteed to have a semantic button/link role, so click
    # it via visible text and a clickable ancestor.
    body = _body_text(page)
    if "app module" in body.lower():
        clicked = generic_click(page, ("APP MODULE", "App Module", "Application Module"))
        if clicked:
            dump_ui(page, "app_module_opened")

    if "dmz" in joined or "port trigger" in joined:
        broad = ("NAT", "Firewall", "Security", "Advanced", "Network Setting")
    else:
        broad = ("Firewall", "Security", "NAT", "Advanced", "Network Setting")

    attempted: set[str] = set()
    for round_no in range(10):
        body = _body_text(page)
        if _has_any(body, specific):
            clicked = generic_click(page, specific)
            if clicked:
                dump_ui(page, f"target_{round_no}")
                body = _body_text(page)
            if _has_any(body, specific):
                return True

        clicked_any = False
        for word in broad:
            if word.lower() in attempted:
                continue
            if word.lower() not in body.lower():
                continue
            attempted.add(word.lower())
            clicked = generic_click(page, (word,))
            if clicked:
                dump_ui(page, f"broad_{round_no}_{re.sub(r'[^A-Za-z0-9]+','_',word)}")
                clicked_any = True
                break
        if clicked_any:
            continue

        # Some menus are icon/tile based and only become discoverable after
        # reopening APP MODULE.
        if "app module" in body.lower() and "app module" not in attempted:
            attempted.add("app module")
            if generic_click(page, ("APP MODULE", "App Module")):
                dump_ui(page, f"app_module_retry_{round_no}")
                continue
        break

    dump_ui(page, "navigate_failed")
    return _has_any(_body_text(page), specific)


def main() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise RuntimeError("NR2301_WRITE_INTEGRATION=1 is required")
    if not os.environ.get("NR2301_PASSWORD"):
        raise RuntimeError("NR2301_PASSWORD is required")

    base.click_button = click_button_v2
    base.navigate = navigate_v2
    try:
        base.main()
    finally:
        (ROOT / "firewall_webui_v2_discovery.json").write_text(
            json.dumps(DISCOVERY, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(f"FIREWALL_WEBUI_AUTOPILOT_V2_EVIDENCE_DIR = {ROOT}")


if __name__ == "__main__":
    main()
