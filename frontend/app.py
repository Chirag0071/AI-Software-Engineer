"""Streamlit dashboard for the AI Software Engineer backend.

Run:  streamlit run frontend/app.py
Backend must be running: uvicorn backend.main:app --reload
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import requests
import streamlit as st

API = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="AI Software Engineer", page_icon="🤖", layout="wide")

st.markdown(
    """
<style>
.block-container {padding-top: 2rem; max-width: 1300px;}
.hero {background: linear-gradient(135deg,#4f46e5 0%,#7c3aed 55%,#db2777 100%);
  padding: 1.4rem 1.8rem; border-radius: 16px; color: white; margin-bottom: 1.2rem;}
.hero h1 {margin:0; font-size: 1.8rem; color:white;}
.hero p {margin:.3rem 0 0; opacity:.9;}
.pipe {display:flex; gap:8px; flex-wrap:wrap; margin: .5rem 0 1rem;}
.stage {flex:1; min-width:110px; padding:.6rem .5rem; border-radius:12px; text-align:center;
  font-size:.8rem; font-weight:600; border:1px solid rgba(128,128,128,.25);}
.stage.pending {opacity:.45;}
.stage.running {background:#fef3c7; color:#92400e; border-color:#f59e0b; animation:pulse 1.2s infinite;}
.stage.done {background:#dcfce7; color:#166534; border-color:#22c55e;}
.stage.failed {background:#fee2e2; color:#991b1b; border-color:#ef4444;}
@keyframes pulse {0%,100%{box-shadow:0 0 0 0 rgba(245,158,11,.5)}50%{box-shadow:0 0 0 6px rgba(245,158,11,0)}}
.badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:.75rem; font-weight:700;}
.b-high {background:#fee2e2; color:#991b1b;} .b-medium {background:#fef3c7; color:#92400e;}
.b-low {background:#e0f2fe; color:#075985;} .b-ok {background:#dcfce7; color:#166534;}
</style>
""",
    unsafe_allow_html=True,
)

STAGES = [
    ("repository_analyst", "🔍 Analyst"),
    ("repository_intelligence", "🧠 Intelligence"),
    ("planner", "📝 Planner"),
    ("coder", "💻 Coder"),
    ("test_agent", "🧪 Tests"),
    ("debugger", "🐞 Debugger"),
    ("code_review", "🔎 Review"),
    ("human_approval", "🙋 Approval"),
]
TERMINAL_OK = {"completed", "github_pr_created", "github_pr_already_exists"}


def api(method: str, path: str, **kw):
    try:
        r = requests.request(method, f"{API}{path}", timeout=kw.pop("timeout", 30), **kw)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except Exception:
            detail = exc.response.text
        st.error(f"API error: {detail}")
    except requests.RequestException as exc:
        st.error(f"Cannot reach backend at {API}: {exc}")
    return None


def stage_status(state: dict, running: bool) -> dict[str, str]:
    result = {k: "pending" for k, _ in STAGES}
    for ev in state.get("events", []):
        a = ev.get("agent")
        if a in result:
            result[a] = {"started": "running", "completed": "done", "failed": "failed"}.get(
                ev.get("event_type"), result[a]
            )
    if not running:
        for k, v in result.items():
            if v == "running":
                result[k] = "done"
    return result


def pipeline(state: dict, running: bool) -> None:
    sts = stage_status(state, running)
    html = "".join(f'<div class="stage {sts[k]}">{label}</div>' for k, label in STAGES)
    st.markdown(f'<div class="pipe">{html}</div>', unsafe_allow_html=True)


def badge(sev: str) -> str:
    s = (sev or "low").lower()
    cls = {"high": "b-high", "critical": "b-high", "medium": "b-medium"}.get(s, "b-low")
    return f'<span class="badge {cls}">{s.upper()}</span>'


def git_diff(repo: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", repo, "diff", "HEAD"], capture_output=True, text=True, timeout=20
        )
        return out.stdout or out.stderr or ""
    except Exception as exc:  # noqa: BLE001
        return f"Unable to run git diff: {exc}"


def render_run(run_id: str) -> None:
    data = api("GET", f"/runs/{run_id}/full")
    if not data:
        return
    state, running = data["state"], data["running"]
    step = state.get("current_step", "unknown")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", "⏳ Running" if running else ("✅ Done" if step in TERMINAL_OK or step == "waiting_for_human_approval" else "⚠️ Stopped"))
    c2.metric("Current step", step)
    c3.metric("Debug retries", f"{state.get('debug_retry_count', 0)} / {state.get('max_debug_retries', 0)}")
    tr = state.get("test_results", {})
    c4.metric("Tests", "—" if not tr else ("✅ Passing" if tr.get("success") else "❌ Failing"))

    pipeline(state, running)

    for err in state.get("errors", []):
        st.error(err)

    tabs = st.tabs(["📋 Plan", "📂 Context", "🧾 Changes", "🧪 Tests", "🔎 Review", "🕒 Timeline", "✅ Approval"])

    with tabs[0]:
        st.write(state.get("plan_summary") or "_Plan not ready yet…_")
        for t in state.get("plan", []):
            with st.expander(f"Task {t.get('id', '')}: {t.get('title', '')}", expanded=False):
                st.write(t.get("description", ""))
                st.caption("Modify: " + ", ".join(t.get("files_to_modify", []) or ["—"]))
                st.caption("Create: " + ", ".join(t.get("files_to_create", []) or ["—"]))
                if t.get("tests_required"):
                    st.caption("Tests: " + ", ".join(t["tests_required"]))

    with tabs[1]:
        st.write(state.get("repository_summary") or "_Waiting for analysis…_")
        if state.get("architecture_summary"):
            st.info(state["architecture_summary"])
        st.write("**Relevant files**")
        st.code("\n".join(state.get("relevant_files", [])) or "—")
        st.caption(f"{len(state.get('files_analyzed', []))} files scanned")

    with tabs[2]:
        gen, mod = state.get("generated_files", []), state.get("modified_files", [])
        st.write("**Created:** " + (", ".join(gen) or "—"))
        st.write("**Modified:** " + (", ".join(mod) or "—"))
        if gen or mod:
            diff = git_diff(state.get("repository_path", "."))
            st.code(diff or "No tracked diff (new files may be untracked).", language="diff")

    with tabs[3]:
        if tr:
            st.write(f"Sandbox: `{tr.get('sandbox', 'local')}` · {tr.get('duration_seconds', 0)}s · exit {tr.get('return_code')}")
            st.code((tr.get("stdout") or "") + (tr.get("stderr") or ""), language="text")
        else:
            st.caption("No test results yet.")
        dbg = state.get("debugger_result")
        if dbg:
            st.write("**Debugger diagnosis**")
            st.write(dbg.get("diagnosis", ""))
            for f in dbg.get("fix_instructions", []):
                st.markdown(f"- {f}")

    with tabs[4]:
        rv = state.get("review_results", {})
        if rv:
            ok = rv.get("overall_status") == "approved"
            st.markdown(f'<span class="badge {"b-ok" if ok else "b-high"}">{rv.get("overall_status", "").upper()}</span>', unsafe_allow_html=True)
            st.write(rv.get("summary", ""))
            for i in rv.get("issues", []):
                st.markdown(f"{badge(i.get('severity'))} **{i.get('file', '')}** — {i.get('description', '')}", unsafe_allow_html=True)
                if i.get("recommendation"):
                    st.caption("↳ " + i["recommendation"])
            if rv.get("security_concerns"):
                st.warning("**Security concerns**\n\n" + "\n".join(f"- {c}" for c in rv["security_concerns"]))
            for s_ in rv.get("strengths", []):
                st.markdown(f"✅ {s_}")
        else:
            st.caption("Review not run yet.")

    with tabs[5]:
        for ev in reversed(state.get("events", [])):
            icon = {"started": "▶️", "completed": "✅", "failed": "❌"}.get(ev.get("event_type"), "•")
            st.text(f"{ev.get('timestamp', '')[11:19]}  {icon} {ev.get('agent')}: {ev.get('message')}")

    with tabs[6]:
        gh = state.get("github_result", {})
        if step == "waiting_for_human_approval":
            st.warning("Review the changes, then approve to open a GitHub Pull Request.")
            reviewer = st.text_input("Reviewer", "human", key=f"rev-{run_id}")
            comment = st.text_area("Comment", key=f"com-{run_id}")
            a, r = st.columns(2)
            if a.button("✅ Approve & create PR", type="primary", use_container_width=True, key=f"ap-{run_id}"):
                with st.spinner("Creating pull request…"):
                    res = api("POST", f"/runs/{run_id}/approve", json={"reviewer": reviewer, "comment": comment}, timeout=120)
                if res:
                    st.success("Approved."); st.json(res)
            if r.button("⛔ Reject", use_container_width=True, key=f"rj-{run_id}"):
                res = api("POST", f"/runs/{run_id}/reject", json={"reviewer": reviewer, "comment": comment})
                if res:
                    st.info("Rejected."); st.json(res)
        elif gh.get("pr_url"):
            st.success(f"Pull request: {gh['pr_url']}")
        else:
            st.caption("Approval is only available once tests and review have passed.")
            if state.get("approval_result"):
                st.json(state["approval_result"])


# ----------------------------------------------------------------------------
st.markdown(
    '<div class="hero"><h1>🤖 Autonomous AI Software Engineer</h1>'
    "<p>Requirement → plan → code → test → debug → review → human approval → GitHub PR</p></div>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("New task")
    repo = st.text_input("Repository path", value=st.session_state.get("repo", ""), placeholder="/path/to/target-repo")
    req = st.text_area("Requirement", height=140, placeholder="Add a multiply(a, b) function to app.py with pytest tests")
    retries = st.slider("Max debug retries", 0, 10, 3)
    if st.button("🚀 Start run", type="primary", use_container_width=True, disabled=not (repo and req)):
        st.session_state["repo"] = repo
        res = api("POST", "/run/start", json={"requirement": req, "repository_path": repo, "max_debug_retries": retries})
        if res:
            st.session_state["run_id"] = res["run_id"]
    st.divider()
    st.subheader("Previous runs")
    for item in (api("GET", "/runs") or [])[:10]:
        label = f"{'⏳' if item['running'] else '•'} {item['requirement'][:34]}"
        if st.button(label, key=f"h-{item['run_id']}", use_container_width=True):
            st.session_state["run_id"] = item["run_id"]


@st.fragment(run_every=2)
def live() -> None:
    rid = st.session_state.get("run_id")
    if not rid:
        st.info("Enter a repository path and requirement in the sidebar, then press **Start run**.")
        return
    render_run(rid)


live()
