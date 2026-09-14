# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from nr2301 import NR2301Client
from capture_firewall_webui_state import capture

TEST_IP = "203.0.113.77"
TEST_PORT = "65500"
TEST_TRIGGER = "SDK-PT-WEBUI"
USB_RE = re.compile(r"(?is)(set|edit|write|switch|enable|disable).{0,80}(usb|usb_mode|management_mode)|(usb|usb_mode|management_mode).{0,80}(set|edit|write|switch|enable|disable)")
DANGER_RE = re.compile(r"(?i)(usb|engineering|firmware|factory\s*reset|reboot|restart|backup|restore)")


def find(value: object, key: str) -> object | None:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            got = find(child, key)
            if got is not None:
                return got
    elif isinstance(value, list):
        for child in value:
            got = find(child, key)
            if got is not None:
                return got
    return None


def contains(value: object, needle: str) -> bool:
    if isinstance(value, str):
        return needle in value
    if isinstance(value, dict):
        return any(contains(v, needle) for v in value.values())
    if isinstance(value, list):
        return any(contains(v, needle) for v in value)
    return False


def snapshot(root: Path, label: str, client: NR2301Client) -> dict[str, object]:
    value = capture(client)
    (root / f"firewall_webui_{label}.json").write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return value


class Evidence:
    def __init__(self, root: Path, origin: str) -> None:
        self.root, self.origin, self.action = root, origin, "bootstrap"
        self.events: list[dict[str, object]] = []
        self.usb_blocked = False

    def request(self, req: Any) -> None:
        if not req.url.startswith(self.origin):
            return
        headers = {k: v for k, v in dict(req.headers).items()
                   if k.lower() not in {"cookie", "authorization", "x-csrf-token", "x-xsrf-token"}}
        self.events.append({"kind": "request", "action": self.action,
                            "time": datetime.now(timezone.utc).isoformat(),
                            "method": req.method, "url": req.url,
                            "headers": headers, "post_data": req.post_data})

    def response(self, resp: Any) -> None:
        if resp.url.startswith(self.origin):
            self.events.append({"kind": "response", "action": self.action,
                                "time": datetime.now(timezone.utc).isoformat(),
                                "status": resp.status, "url": resp.url})

    def route(self, route: Any, req: Any) -> None:
        probe = f"{req.url}\n{req.post_data or ''}"
        if req.method.upper() not in {"GET", "HEAD", "OPTIONS"} and USB_RE.search(probe):
            self.usb_blocked = True
            self.events.append({"kind": "blocked", "action": self.action,
                                "method": req.method, "url": req.url,
                                "reason": "USB/management-mode mutation blocked"})
            route.abort()
        else:
            route.continue_()

    def save(self) -> None:
        (self.root / "firewall_webui_autopilot_network.json").write_text(
            json.dumps(self.events, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )


def js(page: Any, action: str, words: tuple[str, ...], value: str = "") -> bool:
    return bool(page.evaluate(
        """({action, words, value}) => {
          const bad=/(usb|engineering|firmware|factory\\s*reset|reboot|restart|backup|restore)/i;
          const rx=new RegExp(words.map(x=>x.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')).join('|'),'i');
          const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
          const nodes=[...document.querySelectorAll('label,td,th,div,span,p')];
          let hit=nodes.find(e=>visible(e)&&!bad.test(e.innerText||'')&&rx.test((e.innerText||'').trim())&&(e.innerText||'').length<240);
          if(!hit) return false;
          let box=hit.closest('tr,label,li,form')||hit.closest('div')||hit;
          if(action==='toggle'){
            let e=box.querySelector('input[type=checkbox],[role=switch],button[role=switch]');
            if(e&&visible(e)){e.click();return true}
            let s=box.querySelector('select');
            if(s&&visible(s)){let o=[...s.options].find(o=>!o.disabled&&o.value!==s.value);if(o){s.value=o.value;s.dispatchEvent(new Event('change',{bubbles:true}));return true}}
          }
          if(action==='clear'){
            let e=[...box.querySelectorAll('input')].find(e=>visible(e)&&(!value||e.value===value))||box.querySelector('input[type=text],input:not([type])');
            if(e){e.value='';e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true}
          }
          return false;
        }""",
        {"action": action, "words": list(words), "value": value},
    ))


def click_button(page: Any, words: tuple[str, ...]) -> bool:
    rx = re.compile("|".join(re.escape(x) for x in words), re.I)
    for role in ("button", "link", "menuitem", "tab"):
        try:
            loc = page.get_by_role(role, name=rx).first
            if loc.count() and loc.is_visible():
                text = (loc.inner_text() or "") + " " + (loc.get_attribute("aria-label") or "")
                if not DANGER_RE.search(text):
                    loc.click(timeout=2500)
                    time.sleep(0.6)
                    return True
        except Exception:
            pass
    return False


def navigate(page: Any, words: tuple[str, ...]) -> bool:
    rx = re.compile("|".join(re.escape(x) for x in words), re.I)
    for _ in range(6):
        try:
            if rx.search(page.locator("body").inner_text(timeout=2000)):
                return True
        except Exception:
            pass
        if click_button(page, words):
            continue
        if click_button(page, ("Security", "Firewall", "NAT", "Network Setting", "Sicherheit")):
            continue
        break
    return bool(rx.search(page.locator("body").inner_text(timeout=2000)))


def apply(page: Any) -> bool:
    return click_button(page, ("Apply", "Save", "OK", "Übernehmen", "Speichern", "Anwenden"))


def toggle_cycle(page: Any, client: NR2301Client, ev: Evidence, root: Path,
                 label: str, nav_words: tuple[str, ...], ctl_words: tuple[str, ...],
                 group: str, field: str) -> str:
    before = snapshot(root, f"{label}_before", client)
    original = find(before.get(group), field)
    if not navigate(page, nav_words):
        return "SKIPPED_PAGE_NOT_FOUND"
    ev.action = f"{label}_change"
    if not js(page, "toggle", ctl_words):
        return "SKIPPED_CONTROL_NOT_FOUND"
    apply(page); time.sleep(1)
    changed = snapshot(root, f"{label}_changed", client)
    if find(changed.get(group), field) == original:
        return "FAILED_NO_STATE_CHANGE"
    ev.action = f"{label}_restore"
    if not js(page, "toggle", ctl_words):
        return "FAILED_RESTORE_CONTROL_NOT_FOUND"
    apply(page); time.sleep(1)
    restored = snapshot(root, f"{label}_restored", client)
    return "PASS" if find(restored.get(group), field) == original else "FAILED_RESTORE"


def dmz_clear(page: Any, client: NR2301Client, ev: Evidence, root: Path) -> str:
    before = snapshot(root, "dmz_before", client)
    old = find(before.get("dmz_info"), "dmz_dest_ip")
    if not isinstance(old, str) or not old:
        return "NOT_NEEDED_ALREADY_EMPTY"
    if not navigate(page, ("DMZ",)):
        return "SKIPPED_PAGE_NOT_FOUND"
    ev.action = "dmz_clear"
    if not js(page, "clear", ("DMZ",), old):
        return "SKIPPED_INPUT_NOT_FOUND"
    apply(page); time.sleep(1)
    after = snapshot(root, "dmz_after", client)
    return "PASS" if find(after.get("dmz_info"), "dmz_dest_ip") != old else "FAILED_UNCHANGED"


def add_rule(page: Any, client: NR2301Client, ev: Evidence, root: Path,
             label: str, nav_words: tuple[str, ...], kind: str,
             group: str, marker: str) -> str:
    snapshot(root, f"{label}_before", client)
    if not navigate(page, nav_words):
        return "SKIPPED_PAGE_NOT_FOUND"
    ev.action = f"{label}_add"
    if not click_button(page, ("Add", "Add New", "New", "Neu", "Hinzufügen", "Create")):
        return "SKIPPED_ADD_NOT_FOUND"

    values = {"ip": [TEST_IP], "port": [TEST_PORT], "trigger": [TEST_TRIGGER, TEST_PORT, "65501"]}[kind]
    filled = page.evaluate(
        """({kind,values})=>{
          const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
          const ins=[...document.querySelectorAll('input[type=text],input[type=number],input:not([type])')].filter(e=>visible(e)&&!e.disabled);
          let n=0,p=0;
          for(const e of ins){
            const a=((e.name||'')+' '+(e.id||'')+' '+(e.placeholder||'')+' '+(e.getAttribute('aria-label')||'')).toLowerCase();
            let v=null;
            if(kind==='ip'&&/(ip|address|source|destination)/.test(a)) v=values[0];
            if(kind==='port'&&/port/.test(a)) v=values[0];
            if(kind==='trigger'&&/(name|service|description)/.test(a)) v=values[0];
            else if(kind==='trigger'&&/port/.test(a)) v=values[Math.min(1+p++,values.length-1)];
            if(v!==null){e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));n++}
          }
          if(!n&&ins[0]){ins[0].value=values[0];ins[0].dispatchEvent(new Event('input',{bubbles:true}));n=1}
          return n;
        }""",
        {"kind": kind, "values": values},
    )
    if not filled or not apply(page):
        return "SKIPPED_FORM_NOT_UNDERSTOOD"
    time.sleep(1)
    added = snapshot(root, f"{label}_added", client)
    if not contains(added.get(group), marker):
        return "FAILED_ADD_NOT_VISIBLE"

    ev.action = f"{label}_delete"
    ok = page.evaluate(
        """marker=>{
          const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
          const rx=/(delete|remove|löschen|entfernen)/i;
          const nodes=[...document.querySelectorAll('td,div,li,span')];
          const m=nodes.find(e=>visible(e)&&(e.innerText||'').includes(marker));
          if(!m)return false;
          const row=m.closest('tr,li')||m.closest('div')||m;
          const b=[...row.querySelectorAll('button,[role=button],a')].find(e=>visible(e)&&rx.test((e.innerText||'')+' '+(e.title||'')+' '+(e.getAttribute('aria-label')||'')));
          if(!b)return false;b.click();return true;
        }""", marker)
    if not ok:
        return "FAILED_DELETE_CONTROL_NOT_FOUND"
    apply(page); time.sleep(1)
    deleted = snapshot(root, f"{label}_deleted", client)
    return "PASS" if not contains(deleted.get(group), marker) else "FAILED_DELETE_NOT_VISIBLE"


def launch_browser(p: Any, headless: bool) -> Any:
    for channel in ("chrome", "msedge"):
        try:
            return p.chromium.launch(channel=channel, headless=headless)
        except Exception:
            pass
    return p.chromium.launch(headless=headless)


def main() -> None:
    if os.environ.get("NR2301_WRITE_INTEGRATION") != "1":
        raise RuntimeError("NR2301_WRITE_INTEGRATION=1 is required")
    password = os.environ.get("NR2301_PASSWORD")
    if not password:
        raise RuntimeError("NR2301_PASSWORD is required")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            r"Install once: .\.venv\Scripts\python.exe -m pip install playwright"
        ) from exc

    base = os.environ.get("NR2301_URL", "http://zyxel.home").rstrip("/")
    user = os.environ.get("NR2301_USERNAME", "admin")
    root = Path(os.environ.get(
        "NR2301_WEBUI_EVIDENCE_DIR",
        f"firewall_webui_autopilot_{datetime.now():%Y%m%d-%H%M%S}",
    ))
    root.mkdir(parents=True, exist_ok=True)
    origin = f"{urlsplit(base).scheme}://{urlsplit(base).netloc}"
    ev = Evidence(root, origin)
    results: dict[str, str] = {}

    with NR2301Client(base, username=user, password=password, timeout=10.0) as client:
        client.login()
        if not client.session_id:
            raise RuntimeError("SDK login returned no CGISID")
        snapshot(root, "campaign_baseline", client)

        with sync_playwright() as p:
            browser = launch_browser(p, os.environ.get("NR2301_WEBUI_HEADLESS", "1") != "0")
            ctx = browser.new_context(ignore_https_errors=True)
            ctx.add_cookies([{"name": "CGISID", "value": client.session_id, "url": base}])
            page = ctx.new_page()
            page.route("**/*", ev.route)
            page.on("request", ev.request)
            page.on("response", ev.response)
            page.on("dialog", lambda d: d.accept())
            page.goto(base, wait_until="domcontentloaded", timeout=15000)
            time.sleep(1)

            results["admin_from_wan"] = toggle_cycle(
                page, client, ev, root, "admin_from_wan",
                ("Remote Management", "Remote Access", "Firewall", "WAN"),
                ("Admin from WAN", "Remote Administration", "Remote Management"),
                "admin_from_wan", "admin_from_wan_enable",
            )
            results["ping_from_wan"] = toggle_cycle(
                page, client, ev, root, "ping_from_wan",
                ("Ping from WAN", "WAN Ping", "Firewall"),
                ("Ping from WAN", "WAN Ping", "Respond to Ping"),
                "ping_from_wan", "ping_from_wan_enable",
            )
            results["dmz_clear"] = dmz_clear(page, client, ev, root)
            results["ip_filter"] = add_rule(
                page, client, ev, root, "ip_filter",
                ("IP Filter", "IP Filtering", "Firewall"), "ip", "ip_filter_all", TEST_IP,
            )
            results["port_filter"] = add_rule(
                page, client, ev, root, "port_filter",
                ("Port Filter", "Port Filtering", "Firewall"), "port", "port_filter_all", TEST_PORT,
            )
            results["port_trigger"] = add_rule(
                page, client, ev, root, "port_trigger",
                ("Port Trigger", "Port Triggering", "NAT"), "trigger", "port_trigger", TEST_TRIGGER,
            )
            snapshot(root, "campaign_final", client)
            ev.save()
            try:
                page.screenshot(path=str(root / "firewall_webui_autopilot_final.png"), full_page=True)
            except Exception:
                pass
            browser.close()

    failures = {k: v for k, v in results.items() if v not in {"PASS", "NOT_NEEDED_ALREADY_EMPTY"}}
    summary = {"results": results, "usb_mutation_blocked": ev.usb_blocked, "evidence_dir": str(root)}
    (root / "firewall_webui_autopilot_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print("FIREWALL_WEBUI_AUTOPILOT_RESULTS = " + json.dumps(results, sort_keys=True))
    print(f"FIREWALL_WEBUI_AUTOPILOT_USB_BLOCKED = {ev.usb_blocked}")
    print(f"FIREWALL_WEBUI_AUTOPILOT_EVIDENCE_DIR = {root}")
    print(f"FIREWALL_WEBUI_AUTOPILOT_FAILURE_COUNT = {len(failures)}")
    print("FIREWALL_WEBUI_AUTOPILOT = " + ("PASS" if not failures else "PARTIAL"))


if __name__ == "__main__":
    main()
