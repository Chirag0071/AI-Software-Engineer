"""Streamlit dashboard for the AI Software Engineer backend.

Run:  streamlit run frontend/app.py
Backend must be running: uvicorn backend.main:app --reload
"""
from __future__ import annotations

import html as _html
import os

import requests
import streamlit as st

st.set_page_config(
    page_title="AI Software Engineer",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _secret(name: str, default: str = "") -> str:
    try:
        return st.secrets[name]
    except Exception:  # no secrets file
        return os.getenv(name, default)


API = _secret("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = _secret("APP_API_KEY")

ACCENT = "#94D494"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{--bg:#090b0a;--card:#101311;--line:#1f2622;--mut:#8a948e;--txt:#f1f5f2;--g:#94D494;--amb:#f5c26b;--red:#f28b82}
html,body,.stApp,[class*="css"]{font-family:'Inter','Segoe UI',sans-serif}
.stApp{background:var(--bg);background-image:radial-gradient(700px 360px at 80% 0,rgba(148,212,148,.10),transparent 70%)}
[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stSidebar"],[data-testid="collapsedControl"],[data-testid="stSidebarCollapsedControl"],footer,#MainMenu{display:none!important}
.block-container{max-width:1280px;padding:0 40px 80px!important}
.mono{font-family:'JetBrains Mono',Consolas,monospace}
/* nav */
.nav{display:flex;justify-content:space-between;align-items:center;padding:22px 0;border-bottom:1px solid var(--line);margin-bottom:10px}
.logo{display:flex;gap:10px;align-items:center;font-weight:700;font-size:17px;color:var(--txt)}
.logo i{width:26px;height:26px;border-radius:8px;background:var(--g);display:inline-block}
.pill{display:flex;gap:8px;align-items:center;border:1px solid var(--line);border-radius:999px;padding:7px 14px;color:#cfe9cf;font-size:13px}
.pill.off{color:#f0b4ae}
.dot{width:7px;height:7px;border-radius:50%;background:var(--g);box-shadow:0 0 10px var(--g);display:inline-block}
.pill.off .dot{background:var(--red);box-shadow:0 0 10px var(--red)}
/* hero */
.tag{display:inline-block;font-size:12.5px;letter-spacing:.12em;color:var(--g);border:1px solid #27402b;background:#0d150e;border-radius:6px;padding:7px 12px;margin-top:56px}
.hero h1{font-size:64px;line-height:1.04;letter-spacing:-.035em;font-weight:700;margin:26px 0 22px;color:var(--txt);padding:0}
.hero h1 em{font-style:normal;color:var(--g)}
.lead{color:#a3aea7;font-size:18px;line-height:1.65;max-width:540px}
.mini{display:flex;gap:34px;margin-top:30px;color:var(--mut);font-size:13.5px}
.mini b{display:block;color:var(--txt);font-size:22px;margin-bottom:2px}
.term{border:1px solid var(--line);border-radius:16px;background:#0c0f0d;box-shadow:0 30px 90px rgba(0,0,0,.55);overflow:hidden;margin-top:70px}
.th{display:flex;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--line);font-size:12.5px;color:var(--mut)}
.tb{padding:16px 20px;font-size:13px;line-height:2;min-height:300px}
.tb .t{color:#58635c;margin-right:12px}.ok{color:var(--g)}.wr{color:var(--amb)}.er{color:var(--red)}.ag{color:#cdd8d0}
.cur{display:inline-block;width:8px;height:15px;background:var(--g);vertical-align:middle;animation:blink 1s infinite}
@keyframes blink{50%{opacity:0}}
/* stepper */
.flow{margin:46px 0 0;display:flex;align-items:flex-start;position:relative}
.flow:before{content:"";position:absolute;left:18px;right:40px;top:17px;height:2px;background:linear-gradient(90deg,var(--g),#27402b 85%)}
.n{flex:1;position:relative;font-size:14px}
.n .c{width:36px;height:36px;border-radius:50%;background:#0c0f0d;border:2px solid var(--g);color:var(--g);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;position:relative}
.n.fut .c{border-color:#2b3a30;color:#66756b}
.n.now .c{background:var(--g);color:#08120a;box-shadow:0 0 0 6px rgba(148,212,148,.15);animation:glow 1.4s infinite}
.n.bad .c{border-color:var(--red);color:var(--red)}
@keyframes glow{50%{box-shadow:0 0 0 9px rgba(148,212,148,.05)}}
.n b{display:block;margin:14px 0 4px;font-size:14.5px;color:var(--txt)}.n small{color:var(--mut);font-size:12.5px}
.foot{margin:70px 0 0;display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:14px;background:var(--card)}
.foot div{padding:24px 26px;border-right:1px solid var(--line)}.foot div:last-child{border:0}
.foot b{display:block;font-size:26px;color:var(--g);margin-bottom:6px}.foot span{color:var(--mut);font-size:13.5px}
/* run view */
.rtitle{font-size:22px;font-weight:600;margin:6px 0 4px;color:var(--txt)}.rsub{color:var(--mut);font-size:13px}
.box{border:1px solid var(--line);border-radius:12px;background:var(--card);padding:16px 18px;margin-top:12px;color:#dfe7e1;font-size:14px;line-height:1.6}
.box small{color:var(--g);display:block;margin-bottom:6px;font-size:12px;letter-spacing:.05em}
.diff{white-space:pre;overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:#0d110e;padding:14px 16px;font-size:13px;line-height:1.8;margin-top:12px}
.diff .a{color:var(--g);background:rgba(148,212,148,.07);display:block;margin:0 -8px;padding:0 8px}
.diff .d{color:var(--red);background:rgba(242,139,130,.07);display:block;margin:0 -8px;padding:0 8px}
.diff .x{color:#7c877f;display:block}
.stat{border:1px solid var(--line);border-radius:12px;background:var(--card);padding:14px 16px;margin-bottom:10px}
.stat b{font-size:22px;display:block;color:var(--txt)}.stat small{color:var(--mut);font-size:12px}
.appr{border:1px solid #5a4719;background:#15110a;border-radius:12px;padding:14px 16px;font-size:13px;color:#e8d3a2;margin:6px 0 12px}
.runs-h{font-size:11.5px;letter-spacing:.12em;color:var(--mut);margin:18px 0 10px}
.sev{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700;margin-right:8px}
.sev.h{background:rgba(242,139,130,.15);color:var(--red)}.sev.m{background:rgba(245,194,107,.15);color:var(--amb)}.sev.l{background:rgba(148,212,148,.12);color:var(--g)}
.badge-ok{display:inline-block;padding:4px 12px;border-radius:999px;background:rgba(148,212,148,.12);color:var(--g);font-weight:700;font-size:12px}
.badge-bad{display:inline-block;padding:4px 12px;border-radius:999px;background:rgba(242,139,130,.12);color:var(--red);font-weight:700;font-size:12px}
/* streamlit widgets */
.stButton>button,[data-testid^="stBaseButton"]{border-radius:10px!important;border:1px solid var(--line)!important;background:transparent!important;color:#d3dbd5!important;height:3rem;font-weight:600;font-size:15px}
.stButton>button:hover{border-color:#3a5a40!important;color:var(--g)!important}
.stButton>button[kind="primary"],[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-primaryFormSubmit"]{background:var(--g)!important;color:#08120a!important;border-color:var(--g)!important}
.stButton>button[kind="primary"]:hover,[data-testid="stBaseButton-primary"]:hover{background:#a7e0a7!important;color:#08120a!important}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="base-input"]{background:var(--card)!important;border-color:var(--line)!important;border-radius:10px!important}
.stTextInput input,.stTextArea textarea{color:var(--txt)!important}
.stTabs [data-baseweb="tab-list"]{gap:22px;border-bottom:1px solid var(--line)}
.stTabs [data-baseweb="tab"]{color:var(--mut);padding:0 0 12px;background:transparent}
.stTabs [aria-selected="true"]{color:var(--g)!important}
.stTabs [data-baseweb="tab-highlight"]{background:var(--g)!important}
[data-testid="stForm"]{border:1px solid var(--line)!important;border-radius:16px;background:var(--card);padding:28px}
.formhead{font-size:28px;font-weight:700;letter-spacing:-.02em;margin:40px 0 6px;color:var(--txt)}
.formsub{color:var(--mut);margin-bottom:18px}
pre,code{font-family:'JetBrains Mono',Consolas,monospace!important}
"""

STAGES = [
    ("repository_analyst", "Analyse", "Map the repo"),
    ("repository_intelligence", "Context", "Find relevant files"),
    ("planner", "Plan", "Ordered tasks"),
    ("coder", "Code", "Safe file tools"),
    ("test_agent", "Test", "Run pytest"),
    ("debugger", "Debug", "Bounded retries"),
    ("code_review", "Review", "Quality & security"),
    ("human_approval", "Approve", "Human decision"),
]
TERMINAL_OK = {"completed", "github_pr_created", "github_pr_already_exists"}
AWAITING = "waiting_for_human_approval"


def esc(x) -> str:
    return _html.escape(str(x if x is not None else ""))


def html(block: str) -> None:
    """Render raw HTML (indentation stripped so markdown never makes code blocks)."""
    st.markdown(" ".join(line.strip() for line in block.splitlines()), unsafe_allow_html=True)


def api(method: str, path: str, quiet: bool = False, **kw):
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    try:
        r = requests.request(method, f"{API}{path}", headers=headers, timeout=kw.pop("timeout", 30), **kw)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as exc:
        if not quiet:
            try:
                detail = exc.response.json().get("detail", exc.response.text)
            except Exception:
                detail = exc.response.text
            st.error(f"API error: {detail}")
    except requests.RequestException as exc:
        if not quiet:
            st.error(f"Cannot reach backend at {API}: {exc}")
    return None


def goto(view: str, run_id: str | None = None) -> None:
    st.session_state["view"] = view
    if run_id:
        st.session_state["run_id"] = run_id
    st.rerun(scope="app")


# ---------------------------------------------------------------- shared UI
def nav() -> None:
    online = _reachable()
    cls, label = ("", "Backend online") if online else ("off", "Backend offline")
    html(f'<div class="nav"><div class="logo"><i></i>AI Software Engineer</div>'
         f'<div class="pill {cls}"><span class="dot"></span>{label}</div></div>')


def _reachable() -> bool:
    try:
        return requests.get(f"{API}/health", timeout=2).ok
    except requests.RequestException:
        return False


def terminal(events: list[dict], title: str, sample: bool) -> str:
    rows = []
    for ev in events[-9:]:
        t = esc(ev.get("timestamp", "")[11:19])
        kind = ev.get("event_type")
        icon = {"completed": '<span class="ok">✓</span>', "failed": '<span class="er">✕</span>'}.get(kind, '<span class="wr">…</span>')
        rows.append(f'<div><span class="t">{t}</span>{icon} <span class="ag">{esc(ev.get("agent"))}</span> {esc(kind)}</div>')
    if not rows:
        rows = ['<div><span class="t">--:--:--</span><span class="wr">…</span> <span class="ag">waiting</span> for your first run</div>']
    tag = "example" if sample else "latest run"
    return (f'<div class="term"><div class="th mono"><span>{esc(title)}</span>'
            f'<span><span class="dot" style="margin-right:6px"></span>{tag}</span></div>'
            f'<div class="tb mono">{"".join(rows)}<div><span class="cur"></span></div></div></div>')


# ---------------------------------------------------------------- views
def view_home() -> None:
    runs = api("GET", "/runs", quiet=True) or []
    events, title, sample = [], "no runs yet", True
    if runs:
        full = api("GET", f"/runs/{runs[0]['run_id']}/full", quiet=True)
        if full:
            events = full["state"].get("events", [])
            title = f"run-{runs[0]['run_id'][:6]}"
            sample = False

    left, right = st.columns([1.1, 0.9], gap="large")
    with left:
        html("""<div class="hero"><span class="tag mono">MULTI-AGENT · HUMAN-IN-THE-LOOP</span>
        <h1>Describe it.<br>Agents build it.<br><em>You approve it.</em></h1>
        <p class="lead">Turn a plain-English requirement into planned, tested and reviewed code.
        Every change waits for your decision before it becomes a pull request.</p></div>""")
        b1, b2, _ = st.columns([1, 1, 0.8])
        if b1.button("Start a new run →", type="primary", use_container_width=True):
            goto("new")
        if b2.button("Previous runs", use_container_width=True, disabled=not runs):
            goto("run", runs[0]["run_id"])
        html("""<div class="mini"><div><b>8</b>specialised agents</div><div><b>38</b>automated tests</div>
        <div><b>0</b>PRs without approval</div></div>""")
    with right:
        html(terminal(events, title, sample))

    steps = [("01", "Analyse", "Map the repository"), ("02", "Plan", "Ordered tasks"), ("03", "Code", "Safe file tools"),
             ("04", "Test &amp; Debug", "Bounded retries"), ("05", "Review", "Quality &amp; security"),
             ("06", "Approve", "Human decision"), ("PR", "Ship", "GitHub")]
    cells = "".join(
        f'<div class="n {"now" if i == 5 else ("fut" if i == 6 else "")}" style="{"flex:.55" if i == 6 else ""}">'
        f'<div class="c">{n}</div><b>{t}</b><small>{s}</small></div>' for i, (n, t, s) in enumerate(steps))
    html(f'<div class="flow">{cells}</div>')
    html("""<div class="foot"><div><b>Plan → PR</b><span>Full workflow in one run</span></div>
    <div><b>Bounded</b><span>Retry budget, never endless loops</span></div>
    <div><b>Auditable</b><span>Every agent step is logged</span></div>
    <div><b>Human-gated</b><span>Nothing ships without approval</span></div></div>""")


def view_new() -> None:
    _, mid, _ = st.columns([1, 1.6, 1])
    with mid:
        html('<div class="formhead">Start a new run</div>'
             '<div class="formsub">Point the agents at a repository and describe the change you want.</div>')
        with st.form("new_run"):
            repo = st.text_input("Repository path or GitHub URL", value=st.session_state.get("repo", ""),
                                 placeholder="/path/to/repo  or  https://github.com/owner/repo")
            req = st.text_area("Requirement", height=130,
                               placeholder="Add a multiply(a, b) function to app.py with pytest tests")
            retries = st.slider("Max debug retries", 0, 10, 3)
            go = st.form_submit_button("🚀 Start run", type="primary", use_container_width=True)
        if st.button("← Back", key="back_home"):
            goto("home")
        if go:
            if not repo.strip() or not req.strip():
                st.warning("Please enter both a repository and a requirement.")
                return
            st.session_state["repo"] = repo
            res = api("POST", "/run/start", json={"requirement": req, "repository_path": repo, "max_debug_retries": retries})
            if res:
                goto("run", res["run_id"])


def stage_status(state: dict, running: bool) -> dict[str, str]:
    result = {k: "pending" for k, *_ in STAGES}
    for ev in state.get("events", []):
        a = ev.get("agent")
        if a in result:
            result[a] = {"started": "running", "completed": "done", "failed": "failed"}.get(ev.get("event_type"), result[a])
    if not running:
        for k, v in result.items():
            if v == "running":
                result[k] = "done"
    return result


def stepper(state: dict, running: bool) -> None:
    sts = stage_status(state, running)
    cells = []
    for i, (key, label, sub) in enumerate(STAGES, 1):
        cls = {"done": "", "running": "now", "failed": "bad", "pending": "fut"}[sts[key]]
        mark = "✓" if sts[key] == "done" else ("✕" if sts[key] == "failed" else f"{i:02d}")
        cells.append(f'<div class="n {cls}"><div class="c">{mark}</div><b>{label}</b><small>{sub}</small></div>')
    html(f'<div class="flow" style="margin-top:22px">{"".join(cells)}</div>')


def diff_html(diff: str) -> str:
    lines = []
    for ln in diff.splitlines():
        cls = "a" if ln.startswith("+") and not ln.startswith("+++") else "d" if ln.startswith("-") and not ln.startswith("---") else "x"
        lines.append(f'<span class="{cls}">{esc(ln)}</span>')
    return f'<div class="diff mono">{"".join(lines)}</div>'


def stat(value: str, label: str, color: str | None = None) -> str:
    style = f' style="color:{color}"' if color else ""
    return f'<div class="stat"><b{style}>{value}</b><small>{label}</small></div>'


def run_panel(run_id: str) -> None:
    data = api("GET", f"/runs/{run_id}/full")
    if not data:
        return
    state, running = data["state"], data["running"]
    step = state.get("current_step", "unknown")
    tr = state.get("test_results", {})
    rv = state.get("review_results", {})
    gh = state.get("github_result", {})
    files = len(set(state.get("generated_files", []) + state.get("modified_files", [])))
    concerns = len(rv.get("security_concerns", []) or [])

    main, side = st.columns([3, 1.25], gap="large")
    with main:
        status = "Running…" if running else ("Awaiting approval" if step == AWAITING else ("Completed" if step in TERMINAL_OK else "Stopped"))
        html(f'<div class="rtitle">{esc(state.get("user_request", ""))}</div>'
             f'<div class="rsub">{esc(state.get("repository_path", ""))} · {status} · step: {esc(step)}</div>')
        stepper(state, running)
        for err in state.get("errors", []):
            st.error(err)

        t_plan, t_chg, t_test, t_rev, t_time = st.tabs(["Plan", "Changes", "Tests", "Review", "Timeline"])
        with t_plan:
            html(f'<div class="box">{esc(state.get("plan_summary") or "Plan not ready yet…")}</div>')
            for t in state.get("plan", []):
                with st.expander(f"Task {t.get('id', '')}: {t.get('title', '')}"):
                    st.write(t.get("description", ""))
                    st.caption("Modify: " + ", ".join(t.get("files_to_modify", []) or ["—"]))
                    st.caption("Create: " + ", ".join(t.get("files_to_create", []) or ["—"]))
            if state.get("architecture_summary"):
                html(f'<div class="box"><small>ARCHITECTURE</small>{esc(state["architecture_summary"])}</div>')
        with t_chg:
            gen, mod = state.get("generated_files", []), state.get("modified_files", [])
            if gen or mod:
                html(f'<div class="rsub" style="margin-top:12px">Created: {esc(", ".join(gen) or "—")} · Modified: {esc(", ".join(mod) or "—")}</div>')
                d = (api("GET", f"/runs/{run_id}/diff", quiet=True) or {}).get("diff", "")
                html(diff_html(d) if d else '<div class="box">No tracked diff (new files may be untracked).</div>')
            else:
                html('<div class="box">No changes yet…</div>')
        with t_test:
            if tr:
                ok = tr.get("success")
                html(f'<div style="margin-top:12px"><span class="{"badge-ok" if ok else "badge-bad"}">{"PASSING" if ok else "FAILING"}</span>'
                     f' <span class="rsub">{esc(tr.get("sandbox", "local"))} · {esc(tr.get("duration_seconds", 0))}s · exit {esc(tr.get("return_code"))}</span></div>')
                st.code((tr.get("stdout") or "") + (tr.get("stderr") or "") or "(no output)", language="text")
            else:
                html('<div class="box">No test results yet.</div>')
            dbg = state.get("debugger_result")
            if dbg:
                html(f'<div class="box"><small>DEBUGGER DIAGNOSIS</small>{esc(dbg.get("diagnosis", ""))}</div>')
        with t_rev:
            if rv:
                ok = rv.get("overall_status") == "approved"
                html(f'<div style="margin-top:12px"><span class="{"badge-ok" if ok else "badge-bad"}">{esc(rv.get("overall_status", "")).upper()}</span></div>'
                     f'<div class="box">{esc(rv.get("summary", ""))}</div>')
                for i in rv.get("issues", []):
                    sev = (i.get("severity") or "low").lower()
                    c = {"high": "h", "critical": "h", "medium": "m"}.get(sev, "l")
                    rec = f'<br><span class="rsub">↳ {esc(i["recommendation"])}</span>' if i.get("recommendation") else ""
                    html(f'<div class="box"><span class="sev {c}">{sev.upper()}</span><b>{esc(i.get("file", ""))}</b> — {esc(i.get("description", ""))}{rec}</div>')
                if concerns:
                    html('<div class="box" style="border-color:#5a4719"><small style="color:#f5c26b">SECURITY CONCERNS</small>'
                         + "<br>".join("• " + esc(c) for c in rv["security_concerns"]) + "</div>")
            else:
                html('<div class="box">Review has not run yet.</div>')
        with t_time:
            rows = []
            for ev in reversed(state.get("events", [])):
                kind = ev.get("event_type")
                icon = {"completed": '<span class="ok">✓</span>', "failed": '<span class="er">✕</span>'}.get(kind, '<span class="wr">…</span>')
                rows.append(f'<div><span class="t">{esc(ev.get("timestamp", "")[11:19])}</span>{icon} <span class="ag">{esc(ev.get("agent"))}</span> {esc(ev.get("message"))}</div>')
            html(f'<div class="term" style="margin-top:12px"><div class="tb mono" style="min-height:0">{"".join(rows) or "No events yet."}</div></div>')

    with side:
        tests_txt, tests_col = (("—", None) if not tr else (("Pass", ACCENT) if tr.get("success") else ("Fail", "#f28b82")))
        html(stat(tests_txt, "Tests", tests_col)
             + stat(f"{state.get('debug_retry_count', 0)} / {state.get('max_debug_retries', 0)}", "Debug retries used")
             + stat(str(files), "Files changed")
             + stat(str(concerns), "Security concerns"))
        if step == AWAITING:
            html('<div class="appr">Review the changes, then approve to open a GitHub pull request.</div>')
            comment = st.text_input("Comment (optional)", key=f"com-{run_id}")
            if st.button("Approve & create PR", type="primary", use_container_width=True, key=f"ap-{run_id}"):
                with st.spinner("Creating pull request…"):
                    res = api("POST", f"/runs/{run_id}/approve", json={"reviewer": "human", "comment": comment}, timeout=120)
                if res:
                    st.success("Approved."); st.json(res)
            if st.button("Reject", use_container_width=True, key=f"rj-{run_id}"):
                res = api("POST", f"/runs/{run_id}/reject", json={"reviewer": "human", "comment": comment})
                if res:
                    st.info("Rejected.")
        elif gh.get("pr_url"):
            html(f'<div class="appr" style="border-color:#27402b;background:#0d150e;color:#cfe9cf">Pull request created<br><a href="{esc(gh["pr_url"])}" target="_blank" style="color:#94D494">{esc(gh["pr_url"])}</a></div>')
        else:
            html('<div class="appr">Approval unlocks once tests and review have passed.</div>')


@st.fragment(run_every=2)
def view_run() -> None:
    runs = api("GET", "/runs", quiet=True) or []
    current = st.session_state.get("run_id") or (runs[0]["run_id"] if runs else None)
    left, right = st.columns([1, 4.4], gap="large")
    with left:
        if st.button("＋ New run", type="primary", use_container_width=True):
            goto("new")
        html('<div class="runs-h">RUNS</div>')
        for item in runs[:12]:
            mark = "● " if item["run_id"] == current else ""
            icon = "⏳ " if item["running"] else ""
            label = f"{mark}{icon}{(item['requirement'] or 'untitled')[:30]}"
            if st.button(label, key=f"h-{item['run_id']}", use_container_width=True):
                goto("run", item["run_id"])
        if st.button("← Home", key="home_btn", use_container_width=True):
            goto("home")
    with right:
        if current:
            run_panel(current)
        else:
            html('<div class="box">No runs yet. Start one to see it here.</div>')


# ---------------------------------------------------------------- main
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
nav()
view = st.session_state.get("view", "home")
{"home": view_home, "new": view_new, "run": view_run}.get(view, view_home)()