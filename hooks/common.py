from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path


CACHE_DIR = Path(os.environ.get("TMPDIR", "/tmp")) / "ix-gemini-hooks"
STATUS_CACHE_PATH = CACHE_DIR / "ix-status.json"
BRIEFING_CACHE_PATH = CACHE_DIR / "ix-briefing.txt"
PRO_CACHE_PATH = CACHE_DIR / "ix-pro.json"
ERROR_STORE = Path.home() / ".local" / "share" / "ix" / "plugin" / "errors"

HEALTH_TTL_SECONDS = 30
# Whether @ix/pro is installed changes only when someone installs or removes it,
# and the probe now runs a real command rather than `--help`, so it is cached far
# longer than the health check it used to borrow its TTL from.
PRO_TTL_SECONDS = 3600
BRIEFING_TTL_SECONDS = 600

SHELL_OPERATORS = ("|", "&&", "||", ";", "$(", "`")
SEARCH_COMMANDS = {"grep", "rg"}
READ_COMMANDS = {"cat", "head", "tail", "sed", "awk"}
REGEX_META_RE = re.compile(r"[\\^$\[\](){}|*+?]")
SEARCH_VALUE_OPTIONS = {
    "-A", "-B", "-C", "-e", "-f", "-g", "-m", "-t",
    "--context", "--file", "--glob", "--max-count",
    "--regexp", "--type", "--type-add",
}
READ_SKIP_SUFFIXES = (
    ".bin", ".exe", ".gif", ".gz", ".ico", ".jpeg",
    ".jpg", ".pdf", ".png", ".tar", ".zip",
)
READ_SKIP_SEGMENTS = (
    "/.git/", "/__pycache__/", "/build/", "/dist/",
    "/generated/", "/node_modules/",
)
READ_SKIP_BASENAMES = {
    "cargo.lock", "go.sum", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock",
}

# Patterns emitted by the ix CLI when a Pro command is invoked without Pro installed.
_PRO_FEATURE_RE = re.compile(
    r"requires Ix Pro|Install @ix/pro|is a Ix/pro feature|premium features",
    re.IGNORECASE,
)


# ── IO helpers ───────────────────────────────────────────────────────────────

def read_event() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def emit_json(payload: dict) -> None:
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")


def log(msg: str) -> None:
    """Debug logging — always to stderr so it never corrupts JSON stdout."""
    print(msg, file=sys.stderr)


# ── Workspace ────────────────────────────────────────────────────────────────

def find_workspace_root(cwd: str | None) -> Path:
    start = Path(cwd or os.getcwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".gemini" / "settings.json").exists():
            return candidate
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


# ── Command execution ────────────────────────────────────────────────────────

def run_command(
    argv: list[str], cwd: str | Path | None = None, timeout: int = 10
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def ix_available() -> bool:
    return shutil.which("ix") is not None


# ── Caching ──────────────────────────────────────────────────────────────────

def _write_cache(path: Path, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def ix_healthy(cwd: str | Path | None) -> bool:
    if not ix_available():
        return False
    if STATUS_CACHE_PATH.exists():
        try:
            cached = json.loads(STATUS_CACHE_PATH.read_text())
        except json.JSONDecodeError:
            cached = None
        if isinstance(cached, dict):
            timestamp = float(cached.get("timestamp", 0))
            ok = bool(cached.get("ok", False))
            if time.time() - timestamp < HEALTH_TTL_SECONDS:
                return ok
    result = run_command(["ix", "status"], cwd=cwd, timeout=8)
    ok = bool(result and result.returncode == 0)
    _write_cache(STATUS_CACHE_PATH, {"timestamp": time.time(), "ok": ok})
    return ok


def _is_pro_stub_response(result: subprocess.CompletedProcess[str]) -> bool:
    """True when ix answered with the Pro stub — a definitive 'not a Pro install'.

    The stub's contract is the literal string `The '<name>' command requires Ix
    Pro.` on exit 1. Matching it is what separates "Pro is absent" from "the
    probe happened to fail", which is the difference between a cacheable answer
    and one that must not be cached.
    """
    blob = f"{result.stdout or ''}{result.stderr or ''}"
    return "requires Ix Pro" in blob


def ix_pro_available(cwd: str | Path | None) -> bool:
    if PRO_CACHE_PATH.exists():
        try:
            cached = json.loads(PRO_CACHE_PATH.read_text())
        except json.JSONDecodeError:
            cached = None
        if isinstance(cached, dict):
            timestamp = float(cached.get("timestamp", 0))
            ok = bool(cached.get("ok", False))
            if time.time() - timestamp < PRO_TTL_SECONDS:
                return ok
    # Probe with the real command, not `--help`.
    #
    # Pro commands are always *registered*: without @ix/pro the CLI installs a
    # stub for each one whose action prints "The 'briefing' command requires Ix
    # Pro." and sets exit 1. But `--help` is handled by the arg parser before any
    # action runs, so `ix briefing --help` exits 0 on a stub exactly as it does
    # on the real command. Probing with it reported Pro as available on every
    # OSS install, and the hooks then ran Pro commands that could only fail.
    #
    # Running the command itself is the discriminator: the stub exits 1, the real
    # command exits 0. ix_healthy() is checked before this (before_agent.py), so
    # the backend is already known reachable.
    result = run_command(["ix", "briefing", "--format", "json"], cwd=cwd, timeout=8)
    if result is None:
        # Could not run ix at all (timeout, OSError). Says nothing about Pro.
        return False
    ok = result.returncode == 0
    if not ok and not _is_pro_stub_response(result):
        # A non-zero exit that is NOT the Pro stub is a transient failure — a
        # backend hiccup, an expired session, a slow first call. Returning False
        # for this run is right, but caching it is not: PRO_TTL_SECONDS is an
        # hour, so one blip would suppress every Pro feature for a Pro user
        # until it expires. Leave the cache alone and re-probe next time.
        return False
    _write_cache(PRO_CACHE_PATH, {"timestamp": time.time(), "ok": ok})
    return ok


def briefing_due(ttl_seconds: int = BRIEFING_TTL_SECONDS) -> bool:
    if not BRIEFING_CACHE_PATH.exists():
        return True
    try:
        last_sent = float(BRIEFING_CACHE_PATH.read_text().strip())
    except ValueError:
        return True
    return time.time() - last_sent >= ttl_seconds


def mark_briefing_sent() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BRIEFING_CACHE_PATH.write_text(str(time.time()))


# ── JSON parsing ─────────────────────────────────────────────────────────────

def extract_json_fragment(text: str) -> str | None:
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass
    lines = text.splitlines()
    for index, line in enumerate(lines):
        candidate = "\n".join(lines[index:]).strip()
        if not candidate:
            continue
        if candidate[0] not in {"{", "["}:
            continue
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            continue
    return None


def parse_json_output(text: str) -> dict | list | None:
    fragment = extract_json_fragment(text)
    if not fragment:
        return None
    try:
        return json.loads(fragment)
    except json.JSONDecodeError:
        return None


def run_ix_json(
    argv: list[str], cwd: str | Path | None = None, timeout: int = 10
) -> dict | list | None:
    result = run_command(argv, cwd=cwd, timeout=timeout)
    if not result or result.returncode != 0:
        return None
    return parse_json_output(result.stdout)


def run_ix_text(
    argv: list[str], cwd: str | Path | None = None, timeout: int = 10
) -> str | None:
    result = run_command(argv, cwd=cwd, timeout=timeout)
    if not result or result.returncode != 0:
        return None
    fragment = extract_json_fragment(result.stdout)
    return fragment or result.stdout.strip() or None


# ── Error capture ────────────────────────────────────────────────────────────

def _is_pro_feature_message(message: str, stderr: str | None = None) -> bool:
    combined = f"{message} {stderr or ''}"
    return bool(_PRO_FEATURE_RE.search(combined))


def _redact(s: str) -> str:
    s = re.sub(r"[Bb]earer [A-Za-z0-9._~+/=-]{20,}", "Bearer [REDACTED]", s)
    s = re.sub(r"ghp_[A-Za-z0-9]{36,}", "[REDACTED]", s)
    s = re.sub(r"sk-[A-Za-z0-9-]{32,}", "[REDACTED]", s)
    s = re.sub(r"[Aa][Pp][Ii][-_][Kk]ey=[^ &\"']*", "API_KEY=[REDACTED]", s)
    s = re.sub(r"[Tt]oken=[^ &\"']*", "TOKEN=[REDACTED]", s)
    s = s.replace(str(Path.home()), "~")
    return s


def _fingerprint(type_: str, component: str, message: str) -> str:
    norm = f"{type_}|{component}|{message}".lower()
    norm = re.sub(r"\d+", "N", norm)
    norm = re.sub(r"/[^/ ]*", "", norm)
    return hashlib.md5(norm[:120].encode()).hexdigest()


def capture_error_async(
    type_: str,
    component: str,
    message: str,
    exit_code: int,
    command: str = "",
    stderr: str = "",
) -> None:
    """Log an error locally. Skips Pro feature messages."""
    if _is_pro_feature_message(message, stderr):
        return
    try:
        clean_msg = _redact(message)[:150]
        clean_stderr = _redact("\n".join(stderr.split("\n")[:5]))[:300] if stderr else ""
        clean_cmd = _redact(command) if command else ""
        fp = _fingerprint(type_, component, clean_msg)

        ERROR_STORE.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "fp": fp,
            "type": type_,
            "component": component,
            "message": clean_msg,
            "command": clean_cmd,
            "exit_code": exit_code,
            "stderr": clean_stderr,
        })
        log_file = ERROR_STORE / "errors.jsonl"
        with open(log_file, "a") as f:
            f.write(entry + "\n")
    except Exception:
        pass


# ── Pattern detection ────────────────────────────────────────────────────────

def looks_plain_pattern(pattern: str) -> bool:
    return bool(pattern) and not REGEX_META_RE.search(pattern)


def extract_search_pattern(command: str) -> str | None:
    if not command or any(op in command for op in SHELL_OPERATORS):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens:
        return None
    if tokens[0] == "git" and len(tokens) > 1 and tokens[1] == "grep":
        tokens = tokens[1:]
    if tokens[0] not in SEARCH_COMMANDS:
        return None
    for index, token in enumerate(tokens[1:], start=1):
        if token in {"-e", "--regexp"} and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith("--regexp="):
            return token.split("=", 1)[1]
    skip_next = False
    for token in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if token in SEARCH_VALUE_OPTIONS:
            skip_next = True
            continue
        if any(token.startswith(p) for p in ("--glob=", "--max-count=", "--type=")):
            continue
        if token.startswith("-"):
            continue
        return token
    return None


def extract_read_path(command: str) -> str | None:
    if not command or any(op in command for op in SHELL_OPERATORS):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens or tokens[0] not in READ_COMMANDS:
        return None
    candidates = [t for t in tokens[1:] if not t.startswith("-")]
    if not candidates:
        return None
    if tokens[0] == "awk" and len(candidates) >= 2:
        return candidates[-1]
    if tokens[0] == "sed" and len(candidates) >= 2:
        return candidates[-1]
    return candidates[-1]


def skip_read_path(file_path: str) -> bool:
    lowered = file_path.lower()
    if lowered.endswith(READ_SKIP_SUFFIXES):
        return True
    if any(seg in lowered for seg in READ_SKIP_SEGMENTS):
        return True
    if Path(lowered).name in READ_SKIP_BASENAMES:
        return True
    return False


# ── Result summarizers ───────────────────────────────────────────────────────

def summarize_text_results(payload: dict | list | None) -> str:
    if isinstance(payload, dict):
        items = payload.get("results", [])
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    if not isinstance(items, list) or not items:
        return ""
    paths: list[str] = []
    for item in items:
        if isinstance(item, dict) and item.get("path"):
            name = Path(str(item["path"])).name
            if name and name not in paths:
                paths.append(name)
            if len(paths) == 4:
                break
    count = len(items)
    files = ", ".join(paths)
    more = max(0, count - 4)
    summary = f"{count} text hits"
    if files:
        summary += f" in {files}"
    if more:
        summary += f" (+{more} more)"
    return summary


def summarize_locate_results(payload: dict | list | None) -> str:
    if not isinstance(payload, dict):
        return ""
    resolved = payload.get("resolvedTarget")
    if isinstance(resolved, dict) and resolved.get("name"):
        kind = str(resolved.get("kind") or "")
        path = Path(str(resolved.get("path") or "")).name
        suffix = ""
        if kind and path:
            suffix = f" ({kind}, {path})"
        elif kind:
            suffix = f" ({kind})"
        elif path:
            suffix = f" ({path})"
        return f"symbol: {resolved['name']}{suffix}"
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        return ""
    names: list[str] = []
    for c in candidates[:3]:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        label = c["name"]
        kind = str(c.get("kind") or "")
        if kind:
            label += f" ({kind})"
        names.append(label)
    return "candidates: " + ", ".join(names) if names else ""


def summarize_impact(payload: dict | list | None) -> str:
    if not isinstance(payload, dict):
        return ""
    risk_level = str(payload.get("riskLevel") or "unknown").lower()
    summary = payload.get("summary", {})
    direct = int(summary.get("directDependents", 0) or 0) if isinstance(summary, dict) else 0
    member = int(summary.get("memberLevelCallers", 0) or 0) if isinstance(summary, dict) else 0
    effective = max(direct, member)
    if risk_level in {"unknown", "low"} or effective <= 2:
        return ""
    if risk_level == "critical":
        return f"CRITICAL: {effective} dependents"
    if risk_level == "high":
        return f"HIGH RISK: {effective} dependents"
    if risk_level == "medium":
        return f"{effective} dependents"
    return ""


def summarize_overview(payload: dict | list | None) -> str:
    if not isinstance(payload, dict):
        return ""
    key_items = payload.get("keyItems", [])
    names = [
        str(item.get("name"))
        for item in key_items[:5]
        if isinstance(item, dict) and item.get("name")
    ]
    children = payload.get("childrenByKind", {})
    parts = []
    if isinstance(children, dict):
        for kind, count in children.items():
            parts.append(f"{count} {kind}")
    if not names:
        return ""
    summary = "key: " + ", ".join(names)
    if parts:
        summary += " (" + ", ".join(parts) + ")"
    return summary


def summarize_inventory(payload: dict | list | None) -> str:
    if not isinstance(payload, dict):
        return ""
    summary_obj = payload.get("summary", {})
    results = payload.get("results", [])
    total = 0
    if isinstance(summary_obj, dict):
        total = int(summary_obj.get("total", 0) or 0)
    if total == 0 and isinstance(results, list):
        total = len(results)
    if total == 0:
        return ""
    sample = []
    if isinstance(results, list):
        for item in results[:5]:
            if isinstance(item, dict) and item.get("name"):
                sample.append(str(item["name"]))
    text = f"{total} entities"
    if sample:
        text += ": " + ", ".join(sample)
        if total > len(sample):
            text += " ..."
    return text


# ── Parallel execution ───────────────────────────────────────────────────────

def run_parallel_json(
    calls: list[tuple[str, list[str], int]], cwd: str | Path | None
) -> dict[str, dict | list | None]:
    results: dict[str, dict | list | None] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(calls) or 1) as executor:
        future_map = {
            executor.submit(run_ix_json, argv, cwd=cwd, timeout=timeout): name
            for name, argv, timeout in calls
        }
        for future in concurrent.futures.as_completed(future_map):
            results[future_map[future]] = future.result()
    return results


# ── Message builders ─────────────────────────────────────────────────────────

def build_search_message(pattern: str, cwd: str | Path | None) -> str | None:
    if len(pattern) < 3:
        return None
    calls: list[tuple[str, list[str], int]] = [
        ("text", ["ix", "text", pattern, "--limit", "15", "--format", "json"], 10),
    ]
    if looks_plain_pattern(pattern):
        calls.append(("locate", ["ix", "locate", pattern, "--limit", "5", "--format", "json"], 10))
    results = run_parallel_json(calls, cwd)

    text_part = summarize_text_results(results.get("text"))
    locate_part = summarize_locate_results(results.get("locate"))
    if not text_part and not locate_part:
        return None

    pieces = [f"[ix] shell grep intercepted for '{pattern}'"]
    if locate_part:
        pieces.append(locate_part)
    if text_part:
        pieces.append(text_part)
    pieces.append(f"Prefer: ix text '{pattern}' or ix locate '{pattern}' over shell grep")
    return " | ".join(pieces)


def build_read_message(file_path: str, cwd: str | Path | None) -> str | None:
    if not file_path or skip_read_path(file_path):
        return None
    filename = Path(file_path).name
    if not filename:
        return None
    results = run_parallel_json(
        [
            ("inventory", ["ix", "inventory", "--kind", "file", "--path", filename, "--format", "json"], 10),
            ("overview", ["ix", "overview", filename, "--format", "json"], 10),
            ("impact", ["ix", "impact", filename, "--format", "json"], 10),
        ],
        cwd,
    )
    entity_part = summarize_overview(results.get("overview")) or summarize_inventory(results.get("inventory"))
    risk_part = summarize_impact(results.get("impact"))
    if not entity_part and not risk_part:
        return None
    pieces = [f"[ix] {filename}"]
    if entity_part:
        pieces.append(entity_part)
    if risk_part:
        pieces.append(risk_part)
    pieces.append("Use ix read <symbol> to get just a symbol's source")
    return " | ".join(pieces)


def spawn_background_ix_map(cwd: str | Path | None) -> None:
    try:
        subprocess.Popen(
            ["ix", "map"],
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        log(f"[ix] spawn_background_ix_map failed (non-fatal): {exc}")
