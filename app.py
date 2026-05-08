"""
app.py
======
Streamlit chat UI for the OT-2 Protocol Pipeline.
User types natural language; Gemini interprets it and calls the pipeline.

Run with:  streamlit run app.py --server.headless true
"""

import json
import os
import time
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")

import streamlit as st

# ── Output directory ──────────────────────────────────────────────────────────
_DOWNLOADS = pathlib.Path.home() / "Downloads" / "OT2_outputs"
_DOWNLOADS.mkdir(parents=True, exist_ok=True)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OT-2 Protocol Assistant",
    page_icon="🧪",
    layout="wide",
)

# ── Session state defaults ────────────────────────────────────────────────────
for key, default in [
    ("onboarded",        False),
    ("user_name",        ""),
    ("lab_name",         ""),
    ("session_name",     ""),
    ("messages",         []),
    ("pipeline_results", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── Onboarding screen ─────────────────────────────────────────────────────────
if not st.session_state.onboarded:
    st.title("🧪 OT-2 Protocol Assistant")
    st.subheader("Welcome! Let's get you set up.")
    st.markdown("This tool lets you describe a lab protocol in plain English and automatically generates, simulates, analyzes, and visualizes an Opentrons OT-2 script.")
    st.divider()

    # Check for API key
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        st.warning("No Gemini API key found in `.env`. Enter it below or add it to your `.env` file.")
        api_key_input = st.text_input("Gemini API Key", type="password", placeholder="AIza...")
        if api_key_input:
            os.environ["GEMINI_API_KEY"] = api_key_input
    else:
        st.success("✅ Gemini API key detected.")

    with st.form("onboarding_form"):
        st.markdown("#### Tell us about yourself")
        col1, col2 = st.columns(2)
        user_name    = col1.text_input("Your name",    placeholder="e.g. John Doe")
        lab_name     = col2.text_input("Lab / course", placeholder="e.g. BIOE 234 · Spring 2026")
        session_name = st.text_input("Session name (optional)", placeholder="e.g. Dilution Experiment 1")
        submitted = st.form_submit_button("Start →", type="primary", use_container_width=True)

    if submitted:
        st.session_state.user_name    = user_name.strip() or "Researcher"
        st.session_state.lab_name     = lab_name.strip()
        st.session_state.session_name = session_name.strip() or f"Session {time.strftime('%Y-%m-%d')}"
        st.session_state.onboarded    = True
        st.rerun()

    st.stop()


# ── Load pipeline (cached) ────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading pipeline…")
def _load_pipeline():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from modules.opentrons._lib.generator import generate_ot2_script, generate_freeform_script
    from modules.opentrons._lib.simulation_engine import run_opentrons_simulation
    from modules.opentrons._lib.analyzer import analyze_optimization
    from modules.opentrons._lib.visualizer.log_parser import parse_log
    from modules.opentrons._lib.visualizer.state_tracker import build_snapshots
    from modules.opentrons._lib.visualizer.report_generator import generate_report
    from modules.opentrons._lib.visualizer.html_exporter import export_html
    from modules.opentrons._lib.visualizer.deck_visualizer import create_gif
    from modules.opentrons._lib.visualizer.stats_visualizer import render_stats_dashboard

    python_path = os.environ.get("OT_VENV_PYTHON") or sys.executable
    venv_bin = os.path.dirname(python_path)
    suffix = ".exe" if sys.platform == "win32" else ""
    sim_path = os.path.join(venv_bin, f"opentrons_simulate{suffix}")

    return dict(
        generate_ot2_script=generate_ot2_script,
        generate_freeform_script=generate_freeform_script,
        run_opentrons_simulation=run_opentrons_simulation,
        analyze_optimization=analyze_optimization,
        parse_log=parse_log,
        build_snapshots=build_snapshots,
        generate_report=generate_report,
        export_html=export_html,
        create_gif=create_gif,
        render_stats_dashboard=render_stats_dashboard,
        sim_path=sim_path,
    )


def _run_pipeline(params: dict) -> dict:
    """Run all four stages and return a results dict. GIF always generated."""
    import matplotlib.pyplot as plt
    plt.close("all")  # clear any stale figures from a previous run

    pipe = _load_pipeline()
    run_id = f"run_{int(time.time() * 1000)}"  # milliseconds — avoids key collision on rapid re-runs
    out_dir = _DOWNLOADS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Always use the session name the user entered during onboarding
    session = st.session_state.get("session_name") or params.get("task_type", "Protocol").replace("_", " ").title()
    params.setdefault("metadata", {})
    params["metadata"]["protocolName"] = session
    params["metadata"]["author"] = st.session_state.get("user_name", "Researcher")

    results = {"run_id": run_id, "out_dir": str(out_dir), "errors": {}}
    task_type = params.get("task_type", "")
    freeform_meta = {"protocolName": session, "author": params["metadata"]["author"]}

    def _simulate(script):
        return pipe["run_opentrons_simulation"](
            protocol_code=script,
            sim_path=pipe["sim_path"],
            output_filename=str(out_dir / "simulation_log.txt"),
        )

    # 1 — Generate
    if task_type == "custom":
        description = params.get("description", "")
        script = pipe["generate_freeform_script"](description, freeform_meta)
        results["script"] = script
        sim = _simulate(script)
        if sim["status"] == "error":
            # Self-correction pass — feed error back to Gemini
            script = pipe["generate_freeform_script"](
                description, freeform_meta,
                previous_script=script,
                error_message=sim["logs"][:800],
            )
            results["script"] = script
            sim = _simulate(script)
    else:
        script = pipe["generate_ot2_script"](params)
        results["script"] = script
        sim = _simulate(script)

    # 2 — Simulate result check
    results["sim"] = sim
    if sim["status"] == "error":
        label = "after self-correction" if task_type == "custom" else ""
        results["error"] = f"Simulation failed{' ' + label if label else ''}:\n{sim['logs'][:600]}"
        return results

    log_text = sim["logs"]

    # 3 — Analyze
    try:
        results["analysis"] = pipe["analyze_optimization"](log_text)
    except Exception as exc:
        results["errors"]["analyze"] = str(exc)
        results["analysis"] = {"recommendations": []}

    # 4 — Visualize
    protocol_obj = pipe["parse_log"](log_text)
    protocol_obj.protocol_name = session  # always use the session name from onboarding
    snapshots = pipe["build_snapshots"](protocol_obj)
    results["protocol_name"] = protocol_obj.protocol_name
    results["step_count"] = sim["step_count"]
    results["snapshot_count"] = len(snapshots)

    for key, fname, fn in [
        ("pdf",  "report.pdf",         lambda: pipe["generate_report"](protocol_obj, snapshots, str(out_dir / "report.pdf"))),
        ("html", "dashboard.html",     lambda: pipe["export_html"](protocol_obj, snapshots, str(out_dir / "dashboard.html"))),
    ]:
        try:
            fn()
            results[key] = str(out_dir / fname)
        except Exception as exc:
            results["errors"][key] = str(exc)

    try:
        import matplotlib.pyplot as plt
        fig = pipe["render_stats_dashboard"](protocol_obj, snapshots)
        p = str(out_dir / "stats_dashboard.png")
        fig.savefig(p, dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        results["stats"] = p
    except Exception as exc:
        results["errors"]["stats"] = str(exc)

    # GIF — always generated
    try:
        p = str(out_dir / "deck_animation.gif")
        pipe["create_gif"](snapshots, protocol_obj, p, fps=2.0, verbose=False)
        results["gif"] = p
    except Exception as exc:
        results["errors"]["gif"] = str(exc)

    return results


# ── Gemini setup ──────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _get_gemini_client():
    from google import genai
    from google.genai import types
    api_key = os.environ.get("GEMINI_API_KEY", "")
    return genai.Client(api_key=api_key), types


_TOOL_DECLARATION = {
    "name": "run_ot2_pipeline",
    "description": "Generate, simulate, analyze, and visualize an OT-2 protocol end-to-end. Supports template-based and fully custom protocols.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_type": {
                "type": "string",
                "description": (
                    "One of: serial_dilution, pcr_setup, rt_normalization, custom. "
                    "Use 'custom' for any protocol not covered by the three templates."
                ),
            },
            "parameters_json": {
                "type": "string",
                "description": (
                    "JSON string of parameters. "
                    "For serial_dilution/pcr_setup/rt_normalization: include task-specific fields (volumes, counts, etc.). "
                    "For custom: include a 'description' field with the full protocol description "
                    "(labware, pipettes, volumes, step-by-step logic)."
                ),
            },
        },
        "required": ["task_type", "parameters_json"],
    },
}


def _system_prompt() -> str:
    name    = st.session_state.get("user_name", "Researcher")
    lab     = st.session_state.get("lab_name", "")
    session = st.session_state.get("session_name", "")
    return f"""You are an Opentrons OT-2 lab automation assistant helping {name}{f' from {lab}' if lab else ''}.
You help researchers generate, simulate, analyze, and visualize OT-2 pipetting protocols.

When the user describes a protocol, call run_ot2_pipeline with the appropriate parameters.

IMPORTANT — always include a "metadata" field in parameters_json:
  "metadata": {{"protocolName": "<descriptive name derived from the user's request>", "author": "{name}"}}

For example, if the user asks for a 1:2 serial dilution, use:
  "metadata": {{"protocolName": "1:2 Serial Dilution", "author": "{name}"}}

Supported task types and their key parameters:
- serial_dilution: num_dilutions (2-11), dilution_factor (2/4/5/10), initial_volume (µL)
- pcr_setup: num_samples (1-96), master_mix_volume (µL), sample_volume (µL)
- rt_normalization: num_samples (1-96), target_concentration (ng/µL), final_volume (µL), rt_mm_vol (µL)
- custom: for ANY other protocol. Set parameters_json to {{"description": "<full step-by-step protocol description including labware, pipettes, volumes, and logic>"}}

Use 'custom' whenever the user's request doesn't cleanly map to the three templates above (e.g. reagent addition, plate stamping, pooling, buffer exchange, compound spotting, etc.). Be generous — if in doubt, use custom.

After the pipeline runs, summarize results clearly: mention step count, any optimization recommendations (by severity), and that output files are ready to download.
If something fails, explain what went wrong and suggest a fix.
"""


def _call_gemini(messages: list) -> tuple:
    client, types = _get_gemini_client()

    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))

    config = types.GenerateContentConfig(
        system_instruction=_system_prompt(),
        tools=[types.Tool(function_declarations=[_TOOL_DECLARATION])],
        temperature=0.2,
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=config,
    )

    for part in response.candidates[0].content.parts:
        if hasattr(part, "function_call") and part.function_call:
            fc = part.function_call
            task_type   = fc.args.get("task_type", "")
            params_json = fc.args.get("parameters_json", "{}")

            try:
                params = json.loads(params_json)
            except json.JSONDecodeError:
                params = {}
            params["task_type"] = task_type

            return None, _run_pipeline(params)

    return response.text, None


# ── Main UI ───────────────────────────────────────────────────────────────────
# Sidebar — identity + session info
with st.sidebar:
    st.markdown(f"**{st.session_state.user_name}**")
    if st.session_state.lab_name:
        st.caption(st.session_state.lab_name)
    st.caption(f"📁 {st.session_state.session_name}")
    st.divider()
    st.caption(f"Outputs → `~/Downloads/OT2_outputs/`")
    if st.button("🔄 New session", use_container_width=True):
        for k in ["onboarded", "user_name", "lab_name", "session_name", "messages", "pipeline_results"]:
            del st.session_state[k]
        st.rerun()

st.title("🧪 OT-2 Protocol Assistant")
st.caption(f"Session: {st.session_state.session_name}  ·  BIOE 234 Final Project")

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Pipeline result cards
for res in st.session_state.pipeline_results:
    with st.expander(f"📊 {res.get('protocol_name', 'Protocol')}  ·  {res['run_id']}", expanded=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Simulation steps", res.get("step_count", 0))
        c2.metric("Deck snapshots",   res.get("snapshot_count", 0))
        recs = res.get("analysis", {}).get("recommendations", [])
        c3.metric("Recommendations",  len(recs))

        st.markdown("**Downloads**")
        dl_cols = st.columns(4)
        for col, key, label, mime in zip(
            dl_cols,
            ["pdf",           "html",              "stats",       "gif"],
            ["📄 PDF Report",  "🌐 HTML Dashboard", "📈 Stats PNG", "🎞️ GIF"],
            ["application/pdf","text/html",         "image/png",   "image/gif"],
        ):
            path = res.get(key)
            err  = res["errors"].get(key)
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    col.download_button(label, f.read(), file_name=os.path.basename(path),
                                        mime=mime, use_container_width=True,
                                        key=f"{res['run_id']}_{key}")
            elif err:
                col.caption(f"⚠️ failed")

        if recs:
            st.markdown("**Optimization Recommendations**")
            sev_icon = {"high": "🔴", "med": "🟡", "medium": "🟡", "low": "🟢"}
            for r in recs:
                sev  = r.get("severity", "low")
                icon = sev_icon.get(sev, "⚪")
                with st.expander(f"{icon} [{sev.upper()}] {r.get('issue', r.get('issue_type', ''))}"):
                    st.write(r.get("description") or r.get("message", ""))
                    fix = r.get("suggestion") or r.get("suggested_fix", "")
                    if fix:
                        st.info(f"**Suggested fix:** {fix}")

        with st.expander("🐍 Generated script"):
            st.code(res.get("script", ""), language="python")

# Chat input
if prompt := st.chat_input("Describe your protocol… e.g. 'Set up a 1:2 serial dilution with 8 steps and 100 µL'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            reply, pipeline_results = _call_gemini(st.session_state.messages)

        if pipeline_results:
            if "error" in pipeline_results:
                reply = f"❌ The pipeline failed:\n\n```\n{pipeline_results['error']}\n```"
                st.error(reply)
            else:
                recs = pipeline_results.get("analysis", {}).get("recommendations", [])
                high = sum(1 for r in recs if r.get("severity") == "high")
                med  = sum(1 for r in recs if r.get("severity") in ("med", "medium"))
                low  = sum(1 for r in recs if r.get("severity") == "low")
                reply = (
                    f"✅ Pipeline complete for **{pipeline_results.get('protocol_name', 'your protocol')}**.\n\n"
                    f"- **{pipeline_results.get('step_count', 0)}** simulation steps · "
                    f"**{pipeline_results.get('snapshot_count', 0)}** deck snapshots\n"
                    f"- **{len(recs)}** optimization findings"
                    + (f" ({high} high, {med} med, {low} low)" if recs else " — protocol looks clean!")
                    + "\n\nYour downloads are ready below ⬇️"
                )
                st.markdown(reply)
                st.session_state.pipeline_results.append(pipeline_results)
                st.rerun()
        else:
            st.markdown(reply or "Sorry, I didn't get a response.")

    st.session_state.messages.append({"role": "assistant", "content": reply or ""})
