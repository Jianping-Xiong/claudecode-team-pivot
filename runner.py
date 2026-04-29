#!/usr/bin/env python3
"""Pipeline Runner for claudecode-team-pivot (APP v0.4).

Responsibilities per agent-pipeline-protocol §6:
1. Discovery: scan pipelines/*/pipeline.yaml (skip _-prefixed)
2. Execution: run steps sequentially per pipeline.yaml
3. Data passing: maintain inter-step context
4. Validation: structural (JSON Schema subset) + content (validator scripts)
5. Constructor/destructor: auto-run on every business pipeline
6. Paused/resume: hand LLM steps off to Claude Code via stdout JSON + session state

LLM steps do NOT call an LLM API from inside this runner — we're running
inside Claude Code, which IS the LLM. The paused/resume protocol lets CC
do the LLM work and feed the result back via `runner.py resume`.

LLM 步不在 runner 里调远端 LLM —— 我们跑在 Claude Code 里，CC 就是那个 LLM。
Paused/resume 协议让 CC 做 LLM 工作，通过 `resume` 命令回传结果。

Spec: https://github.com/hashSTACS-Global/agent-pipeline-protocol
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "runner.py requires PyYAML. Install it with:\n"
        "  python -m pip install pyyaml\n"
        "\n"
        "(Only runner.py needs this; bin/pivot.py atomic commands still work "
        "without PyYAML.)\n"
    )
    sys.exit(2)

# Force UTF-8 stdout/stderr. Windows PowerShell defaults to GBK (CP936), which
# crashes print(json.dumps(..., ensure_ascii=False)) on any non-ASCII output.
# Python 3.7+ supports reconfigure(). On older, PYTHONIOENCODING=utf-8 works.
# 强制 stdout UTF-8；Windows PowerShell 默认 GBK 会把中文 JSON 打印炸掉。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APP_ROOT = Path(__file__).resolve().parent
PIPELINES_DIR = APP_ROOT / "pipelines"
SESSIONS_DIR = Path.home() / ".pivot" / "sessions"
SESSION_TTL_SECONDS = 24 * 3600  # 24h — destructor prunes older


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class RunnerError(Exception):
    """Any runner-level failure surfaced as JSON error to the caller."""


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Pipeline discovery
# ---------------------------------------------------------------------------

def discover_pipelines() -> dict[str, dict]:
    """Return {pipeline_name: pipeline_yaml_dict} for business pipelines only.
    _-prefixed dirs are framework hooks, excluded from the routing table.
    业务 pipeline 列表（`_` 开头的目录是框架 hook，不出现在路由表）。
    """
    if not PIPELINES_DIR.is_dir():
        return {}
    out: dict[str, dict] = {}
    for child in PIPELINES_DIR.iterdir():
        if not child.is_dir() or child.name.startswith("_"):
            continue
        yml = child / "pipeline.yaml"
        if not yml.is_file():
            continue
        try:
            data = _load_yaml(yml)
        except Exception as e:
            # Bad yaml — skip and warn via stderr. Don't poison other pipelines.
            print(f"WARN: cannot load {yml}: {e}", file=sys.stderr)
            continue
        name = data.get("name") or child.name
        data["_dir"] = str(child)
        out[name] = data
    return out


def framework_pipeline(name: str) -> Optional[dict]:
    """Return parsed yaml for _constructor / _destructor, or None."""
    d = PIPELINES_DIR / name
    yml = d / "pipeline.yaml"
    if not yml.is_file():
        return None
    data = _load_yaml(yml)
    data["_dir"] = str(d)
    return data


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def render_template(tpl: str, *, input_: dict, steps: dict) -> str:
    """Substitute `{{input.foo}}` and `{{step.output[.field]}}` references.

    Missing refs become empty strings rather than KeyError — keeps prompts
    forgiving when optional fields are unset.
    缺失的引用替换为空串，避免可选字段没填时 prompt 渲染失败。
    """
    def lookup(expr: str) -> str:
        parts = expr.split(".")
        if parts[0] == "input":
            v: Any = input_
            parts = parts[1:]
        elif parts[0] in steps:
            v = steps[parts[0]].get("output")
            parts = parts[1:]
            # Drop literal "output" if present ({{step.output.field}} form)
            if parts and parts[0] == "output":
                parts = parts[1:]
        else:
            return ""
        for p in parts:
            if isinstance(v, dict):
                v = v.get(p)
            else:
                return ""
            if v is None:
                return ""
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False, indent=2)
        return "" if v is None else str(v)

    return _TEMPLATE_RE.sub(lambda m: lookup(m.group(1)), tpl)


# ---------------------------------------------------------------------------
# Schema validation (minimal — type + required + basic property types)
# ---------------------------------------------------------------------------

_JSON_TYPE = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def validate_schema(obj: Any, schema: dict, path: str = "") -> list[str]:
    """Return a list of human-readable errors (empty = valid).
    Supports: type, required, properties, items, enum.
    最小 JSON Schema 子集；够覆盖本 skill 的 schema 需求。
    """
    errors: list[str] = []
    t = schema.get("type")
    if t:
        expected = _JSON_TYPE.get(t)
        if expected and not isinstance(obj, expected):
            errors.append(f"{path or '<root>'}: expected {t}, got {type(obj).__name__}")
            return errors  # short-circuit; downstream checks assume the right type
    enum = schema.get("enum")
    if enum is not None and obj not in enum:
        errors.append(f"{path or '<root>'}: value {obj!r} not in enum {enum}")
    if t == "object" and isinstance(obj, dict):
        for req in schema.get("required", []):
            if req not in obj:
                errors.append(f"{path or '<root>'}: missing required property '{req}'")
        for prop, sub_schema in (schema.get("properties") or {}).items():
            if prop in obj:
                errors.extend(
                    validate_schema(obj[prop], sub_schema, f"{path}.{prop}" if path else prop)
                )
    elif t == "array" and isinstance(obj, list):
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(obj):
                errors.extend(validate_schema(item, item_schema, f"{path}[{i}]"))
    return errors


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------

def _normalize_python_cmd(cmd: str) -> str:
    """Replace a leading `python` / `python3` token with sys.executable.

    macOS Ventura+ only ships `python3`; Windows typically only `python`.
    Pipeline authors shouldn't care — whichever interpreter is running this
    runner.py is the one that should run step scripts too.
    Quote sys.executable since on Windows it may contain spaces
    (`C:\\Program Files\\Python313\\python.exe`).
    macOS 没 `python`，Windows 没 `python3`；pipeline.yaml 不该操心，
    直接用 runner 自己的解释器。路径可能含空格（Windows），要带引号。
    """
    m = re.match(r"^(python3?)(?=\s|$)", cmd)
    if not m:
        return cmd
    return f'"{sys.executable}" {cmd[m.end():].lstrip()}'


def run_code_step(step: dict, pipeline_dir: Path, input_: dict, steps: dict) -> dict:
    """Execute a `code` step as a subprocess. stdin/stdout JSON per spec §4.1."""
    cmd = _normalize_python_cmd(step["command"])
    payload = {"input": input_, "steps": {k: {"output": v.get("output")} for k, v in steps.items()}}
    # Pass PYTHONIOENCODING=utf-8 so step scripts' print() emits UTF-8 bytes,
    # regardless of the Windows console codepage.
    # 子进程 PYTHONIOENCODING=utf-8，避免 Windows 控制台 GBK 污染 stdout。
    child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(APP_ROOT),
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=child_env,
        )
    except FileNotFoundError as e:
        raise RunnerError(f"step '{step['name']}' command not runnable: {e}") from e
    if result.returncode != 0:
        raise RunnerError(
            f"step '{step['name']}' exit={result.returncode}: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    try:
        body = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as e:
        raise RunnerError(
            f"step '{step['name']}' stdout is not JSON: {e}; raw={result.stdout[:500]!r}"
        ) from e
    return body.get("output", {})


def build_llm_request(step: dict, pipeline_dir: Path, input_: dict, steps: dict,
                      previous_errors: Optional[list[str]] = None) -> dict:
    """Render the LLM prompt + resolve the schema. Caller pauses the pipeline
    and hands this request to the invoking agent (Claude Code).
    """
    prompt = render_template(step["prompt"], input_=input_, steps=steps)
    if previous_errors:
        # Inject previous validation errors to retry-prompt (spec §4.2).
        prompt += (
            "\n\n---\nPrevious attempt failed validation with these errors:\n- "
            + "\n- ".join(previous_errors)
            + "\nReturn a corrected response matching the schema."
        )
    req: dict = {"step": step["name"], "prompt": prompt}
    schema_path = step.get("schema")
    if schema_path:
        req["schema"] = _load_json(pipeline_dir / schema_path)
    return req


def run_validator(validate_path: Path, llm_output: Any, input_: dict, steps: dict) -> list[str]:
    """Run a `validate:` script; return error list (empty = pass)."""
    payload = {
        "output": llm_output,
        "input": input_,
        "steps": {k: {"output": v.get("output")} for k, v in steps.items()},
    }
    child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # Use sys.executable so validator scripts run under the same interpreter
    # as runner.py — portable across macOS (python3-only) and Windows.
    result = subprocess.run(
        [sys.executable, str(validate_path)],
        cwd=str(APP_ROOT),
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=child_env,
    )
    if result.returncode == 0:
        return []
    try:
        body = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return [f"validator non-JSON stdout: {result.stdout[:200]}"]
    return body.get("errors") or [f"validator exit={result.returncode}"]


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def new_session_id() -> str:
    return secrets.token_hex(8)


def session_path(sid: str) -> Path:
    return SESSIONS_DIR / f"{sid}.json"


def save_session(sess: dict) -> None:
    _save_json(session_path(sess["session_id"]), sess)


def load_session(sid: str) -> dict:
    p = session_path(sid)
    if not p.is_file():
        raise RunnerError(f"session not found: {sid}")
    return _load_json(p)


def drop_session(sid: str) -> None:
    p = session_path(sid)
    if p.is_file():
        p.unlink()


def prune_expired_sessions() -> int:
    """Destructor duty: sweep sessions older than TTL. Returns count pruned."""
    if not SESSIONS_DIR.is_dir():
        return 0
    now = time.time()
    n = 0
    for p in SESSIONS_DIR.glob("*.json"):
        try:
            if now - p.stat().st_mtime > SESSION_TTL_SECONDS:
                p.unlink()
                n += 1
        except OSError:
            pass
    return n


# ---------------------------------------------------------------------------
# Pipeline execution engine
# ---------------------------------------------------------------------------

def run_constructor_if_present() -> None:
    """Framework guarantee: run _constructor before any business pipeline.
    A constructor failure aborts the pipeline — business does not run.
    """
    ctor = framework_pipeline("_constructor")
    if ctor is None:
        return
    _execute_steps(
        pipeline=ctor,
        pipeline_dir=Path(ctor["_dir"]),
        input_={},
        steps={},
        resume_session=None,
        pipeline_name="_constructor",
    )


def run_destructor_if_present(*, business_error: Optional[str]) -> None:
    """Framework guarantee: always run _destructor after business pipeline.
    Runs in a swallow-errors mode; destructor failure does not mask business
    errors but is reported to stderr.
    跨业务 pipeline 的尾巴清理；自己失败不掩盖业务错误。
    """
    dtor = framework_pipeline("_destructor")
    if dtor is None:
        # Even without a _destructor yaml, do basic housekeeping.
        # 没声明 _destructor 也跑一个基础 housekeeping。
        prune_expired_sessions()
        return
    try:
        _execute_steps(
            pipeline=dtor,
            pipeline_dir=Path(dtor["_dir"]),
            input_={"business_error": business_error or ""},
            steps={},
            resume_session=None,
            pipeline_name="_destructor",
        )
    except Exception as e:
        print(f"WARN: destructor failed: {e}", file=sys.stderr)


def start_pipeline(name: str, input_: dict, pipelines: dict[str, dict]) -> dict:
    """Entry point for a business pipeline. Handles constructor + pipeline +
    destructor. Returns either {"status":"completed", "output":...} or
    {"status":"paused", "session":..., "llm_request":...}.
    """
    if name not in pipelines:
        raise RunnerError(
            f"pipeline '{name}' not found. Available: {sorted(pipelines)}"
        )
    # Constructor is mandatory (if present) — a failure here aborts.
    run_constructor_if_present()

    pipeline = pipelines[name]
    pipeline_dir = Path(pipeline["_dir"])
    business_error: Optional[str] = None
    try:
        return _execute_steps(
            pipeline=pipeline,
            pipeline_dir=pipeline_dir,
            input_=input_,
            steps={},
            resume_session=None,
            pipeline_name=name,
        )
    except RunnerError as e:
        business_error = str(e)
        raise
    finally:
        run_destructor_if_present(business_error=business_error)


def resume_pipeline(sid: str, llm_output: Any) -> dict:
    """Continue a paused pipeline with the LLM output supplied by the agent."""
    sess = load_session(sid)
    pipelines = discover_pipelines()
    if sess["pipeline"] not in pipelines:
        raise RunnerError(f"pipeline '{sess['pipeline']}' vanished since pause")
    pipeline = pipelines[sess["pipeline"]]
    pipeline_dir = Path(pipeline["_dir"])

    # Validate the LLM output against the paused step's schema.
    paused = sess["paused_step"]
    step_defs = {s["name"]: s for s in pipeline["steps"]}
    step = step_defs[paused]
    errors: list[str] = []
    if "schema" in step:
        schema = _load_json(pipeline_dir / step["schema"])
        errors = validate_schema(llm_output, schema)
    if not errors and "validate" in step:
        errors = run_validator(pipeline_dir / step["validate"], llm_output, sess["input"], sess["steps"])

    if errors:
        attempts = sess.get("attempts", 0) + 1
        max_retry = int(step.get("retry", 2))
        if attempts >= max_retry:
            drop_session(sid)
            raise RunnerError(
                f"step '{paused}' exhausted {max_retry} retries. Last errors: {errors}"
            )
        sess["attempts"] = attempts
        sess["llm_request"] = build_llm_request(
            step, pipeline_dir, sess["input"], sess["steps"], previous_errors=errors
        )
        save_session(sess)
        return {
            "status": "paused",
            "session": sid,
            "retry": True,
            "errors": errors,
            "llm_request": sess["llm_request"],
        }

    # Output accepted — record and continue from the next step.
    sess["steps"][paused] = {"output": llm_output}
    sess["attempts"] = 0
    save_session(sess)
    # Resume execution from next step onward.
    return _execute_steps(
        pipeline=pipeline,
        pipeline_dir=pipeline_dir,
        input_=sess["input"],
        steps=sess["steps"],
        resume_session=sess,
        pipeline_name=sess["pipeline"],
    )


def _execute_steps(
    *,
    pipeline: dict,
    pipeline_dir: Path,
    input_: dict,
    steps: dict,
    resume_session: Optional[dict],
    pipeline_name: str,
) -> dict:
    """Core step-execution loop. Handles code steps directly; llm steps save
    a session and return {"status": "paused", ...}.
    """
    step_defs: list[dict] = pipeline.get("steps", [])
    # Where to start: if resuming, pick up AFTER the paused step.
    start_index = 0
    if resume_session:
        for i, s in enumerate(step_defs):
            if s["name"] == resume_session["paused_step"]:
                start_index = i + 1
                break

    for step in step_defs[start_index:]:
        stype = step.get("type", "code")
        if stype == "code":
            try:
                out = run_code_step(step, pipeline_dir, input_, steps)
            except RunnerError:
                raise
            steps[step["name"]] = {"output": out}
        elif stype == "llm":
            # Pause — hand off to the invoking agent.
            sid = resume_session["session_id"] if resume_session else new_session_id()
            llm_request = build_llm_request(step, pipeline_dir, input_, steps)
            sess = {
                "session_id": sid,
                "pipeline": pipeline_name,
                "started_at": (resume_session or {}).get("started_at") or time.time(),
                "paused_step": step["name"],
                "paused_at": time.time(),
                "input": input_,
                "steps": steps,
                "attempts": 0,
                "llm_request": llm_request,
            }
            save_session(sess)
            return {
                "status": "paused",
                "session": sid,
                "llm_request": llm_request,
            }
        else:
            raise RunnerError(f"unknown step type '{stype}' in pipeline '{pipeline_name}'")

    # All steps done — determine final output.
    output_step = pipeline.get("output") or (step_defs[-1]["name"] if step_defs else None)
    final = steps.get(output_step, {}).get("output") if output_step else None

    # Clean up session if we were resuming.
    if resume_session:
        drop_session(resume_session["session_id"])

    return {"status": "completed", "output": final}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_list(_args) -> dict:
    pipelines = discover_pipelines()
    return {
        "status": "completed",
        "output": {
            "pipelines": [
                {
                    "name": name,
                    "description": p.get("description", ""),
                    "triggers": p.get("triggers", []),
                }
                for name, p in sorted(pipelines.items())
            ]
        },
    }


def cmd_run(args) -> dict:
    pipelines = discover_pipelines()
    input_: dict = {}
    if args.input_file:
        input_ = _load_json(Path(args.input_file))
    if args.input_kv:
        for kv in args.input_kv:
            if "=" not in kv:
                raise RunnerError(f"--set expects key=value, got: {kv}")
            k, v = kv.split("=", 1)
            input_[k] = v
    return start_pipeline(args.pipeline, input_, pipelines)


def cmd_resume(args) -> dict:
    if args.llm_output_file:
        llm_output = _load_json(Path(args.llm_output_file))
    elif args.llm_output:
        llm_output = json.loads(args.llm_output)
    else:
        raise RunnerError("resume needs --llm-output or --llm-output-file")
    return resume_pipeline(args.session, llm_output)


def cmd_setup(args) -> dict:
    """Guided first-run setup: collect base_url + token, write config.json,
    then verify by running the constructor.

    Non-interactive if --base-url + --token are both given on CLI (AI agents,
    CI, etc.); otherwise falls back to stdin prompts.
    交互式首次配置；也支持全参数传入走无交互模式（便于 CC / CI 驱动）。
    """
    cfg_path = Path.home() / ".pivot" / "config.json"

    # Prefer existing config as defaults if re-running setup.
    existing: dict = {}
    if cfg_path.is_file():
        try:
            with cfg_path.open(encoding="utf-8-sig") as fh:
                existing = json.load(fh)
        except Exception:
            existing = {}

    base_url = args.base_url or existing.get("base_url") or ""
    token = args.token or existing.get("token") or ""

    # Interactive fallback — TTY only, else error.
    if (not base_url or "YOUR_DOMAIN" in base_url) and sys.stdin.isatty():
        prompt = f"Pivot server URL [{base_url or 'https://pivot.<your-team>.com'}]: "
        entered = input(prompt).strip()
        base_url = entered or base_url
    if (not token or token.startswith("pvt_REPLACE")) and sys.stdin.isatty():
        print(
            "Generate a PAT at your Pivot Web → Settings → API Tokens page "
            f"({base_url.rstrip('/')}/settings/api-tokens if reachable).\n"
            "The plaintext is shown only once — paste it now:",
            file=sys.stderr,
        )
        token = input("PAT token: ").strip()

    if not base_url or "YOUR_DOMAIN" in base_url:
        raise RunnerError(
            "base_url is required. Re-run with --base-url https://pivot.<your-team>.com"
        )
    if not token or token.startswith("pvt_REPLACE"):
        raise RunnerError(
            "token is required. Re-run with --token pvt_xxx (get one from Pivot "
            "Web Settings → API Tokens)"
        )

    cfg = {
        "base_url": base_url.rstrip("/"),
        "token": token,
        "mirror_dir": existing.get("mirror_dir", ""),
    }
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    # Explicit UTF-8 no-BOM write; PS Set-Content -Encoding UTF8 would add a BOM.
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Verify by running the constructor end-to-end.
    try:
        run_constructor_if_present()
    except RunnerError as e:
        raise RunnerError(
            f"config written to {cfg_path}, but constructor still fails: {e}"
        ) from e

    return {
        "status": "completed",
        "output": {
            "config_path": str(cfg_path),
            "base_url": cfg["base_url"],
            "token_len": len(token),
            "next_steps": [
                "python runner.py check-init",
                "python runner.py list",
                "python bin/pivot.py matters --limit 5",
            ],
        },
    }


def cmd_check_init(_args) -> dict:
    cfg = Path.home() / ".pivot" / "config.json"
    ok = cfg.is_file()
    token_ok = False
    if ok:
        try:
            data = _load_json(cfg)
            token_ok = bool(data.get("token") or os.environ.get("PIVOT_TOKEN"))
        except Exception:
            ok = False
    return {
        "status": "completed",
        "output": {
            "initialized": ok and token_ok,
            "config_path": str(cfg),
            "config_exists": cfg.is_file(),
            "token_configured": token_ok,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="runner.py",
        description="Pipeline Runner for claudecode-team-pivot (APP v0.4).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List available pipelines.")
    sub.add_parser("check-init", help="Verify config.json + token.")

    sp = sub.add_parser(
        "setup",
        help="Guided first-run: set base_url + token, verify config.",
    )
    sp.add_argument("--base-url", help="Pivot server URL (skip prompt if given).")
    sp.add_argument("--token", help="PAT token (skip prompt if given).")

    sp = sub.add_parser("resume", help="Resume a paused pipeline with LLM output.")
    sp.add_argument("session")
    grp = sp.add_mutually_exclusive_group(required=True)
    grp.add_argument("--llm-output", help="LLM output JSON as inline string.")
    grp.add_argument("--llm-output-file", help="Path to file containing LLM output JSON.")

    # run <pipeline> — generic runner; individual pipelines get their own
    # subparser too so we can declare typed arguments per pipeline.
    sp = sub.add_parser("run", help="Run a pipeline with generic input.")
    sp.add_argument("pipeline")
    sp.add_argument("--input-file", help="Path to JSON file with pipeline input.")
    sp.add_argument("--set", dest="input_kv", action="append", default=[],
                    help="key=value pair appended to input (repeatable).")

    # Convenience: shortcut subparsers for known pipelines. Discovered lazily
    # so the shape of each pipeline's input can be declared in pipeline.yaml
    # and surfaced as proper CLI flags. For MVP we hand-wire the common ones.
    for name, flags in [
        ("draft", ["thread", "content_file"]),
        ("reply", ["thread", "draft_file", "mention", "mention_comment", "reply_to"]),
        ("read", ["thread"]),
        ("digest", ["since"]),
    ]:
        sp = sub.add_parser(name, help=f"Shortcut for 'run {name}'.")
        for f in flags:
            sp.add_argument(f"--{f.replace('_', '-')}", dest=f)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.cmd == "list":
            result = cmd_list(args)
        elif args.cmd == "check-init":
            result = cmd_check_init(args)
        elif args.cmd == "setup":
            result = cmd_setup(args)
        elif args.cmd == "resume":
            result = cmd_resume(args)
        elif args.cmd == "run":
            result = cmd_run(args)
        else:
            # Shortcut subcommand: treat args.cmd as pipeline name; collect
            # flag values into input dict.
            input_ = {
                k: v for k, v in vars(args).items()
                if k != "cmd" and v is not None
            }
            pipelines = discover_pipelines()
            result = start_pipeline(args.cmd, input_, pipelines)
    except RunnerError as e:
        print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False, indent=2))
        return 1
    except Exception as e:
        print(
            json.dumps(
                {"status": "error", "error": f"unexpected: {type(e).__name__}: {e}"},
                ensure_ascii=False, indent=2,
            )
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
