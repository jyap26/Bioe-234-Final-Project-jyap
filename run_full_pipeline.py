"""
tools/run_full_pipeline.py
===========================
End-to-end pipeline: generate → simulate → analyze → visualize.
Returns a combined JSON summary with results from each stage.
"""

import json
import time
import matplotlib
matplotlib.use("Agg")

from .generate_protocol import _instance as _gen
from .simulate_protocol import _instance as _sim
from .analyze_protocol import _instance as _ana
from .visualize_deck_state import _instance as _viz


class RunFullPipeline:
    def initiate(self) -> None:
        pass

    def run(self, task_type: str, parameters_json: str) -> str:
        run_id = f"run_{int(time.time())}"
        summary: dict = {"run_id": run_id, "stages": {}}

        # 1 — Generate
        gen_result_raw = _gen.run(task_type=task_type, parameters_json=parameters_json)
        gen_result = json.loads(gen_result_raw)
        summary["stages"]["generate"] = gen_result
        if "error" in gen_result:
            summary["status"] = "failed_at_generate"
            return json.dumps(summary)

        script = gen_result["script"]
        summary["stages"]["generate"]["script_lines"] = len(script.splitlines())

        # 2 — Simulate
        sim_result_raw = _sim.run(
            protocol_code=script,
            output_filename=f"{run_id}_simulation.txt",
        )
        sim_result = json.loads(sim_result_raw)
        summary["stages"]["simulate"] = {k: v for k, v in sim_result.items() if k != "log"}
        if "error" in sim_result:
            summary["status"] = "failed_at_simulate"
            return json.dumps(summary)

        sim_log = sim_result.get("log", "")

        # 3 — Analyze
        ana_result_raw = _ana.run(simulation_log=sim_log)
        ana_result = json.loads(ana_result_raw)
        summary["stages"]["analyze"] = ana_result
        if "error" in ana_result:
            summary["status"] = "failed_at_analyze"

        # 4 — Visualize (best-effort even if analysis had errors)
        viz_result_raw = _viz.run(simulation_log=sim_log, run_id=run_id)
        viz_result = json.loads(viz_result_raw)
        summary["stages"]["visualize"] = viz_result

        summary["status"] = "complete"
        return json.dumps(summary)


_instance = RunFullPipeline()
_instance.initiate()
run_full_pipeline = _instance.run
