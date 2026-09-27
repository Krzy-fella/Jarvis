"""
actions.py — Everything that actually touches the outside world.
"""

import os
import re
import subprocess
import shutil
import shlex
import json
import config

class UnsafeCommandError(Exception):
    """Raised when a command matches the destructive-command blacklist."""

def is_command_safe(command: str) -> bool:
    """Return True if `command` does not match any blacklisted pattern."""
    for pattern in config.BLACKLISTED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False
    return True

from tool_inventory import KALI_TOOLSET
from file_tools import create_file, read_file, edit_file
from devices import connect_device

ALLOWED_TOOLS = {tool: [tool] for cat in KALI_TOOLSET.values() for tool in cat}

def kali_tool(tool_name: str, argument_string: str, timeout: int | None = None) -> str:
    timeout = config.TOOL_TIMEOUT if timeout is None else timeout
    if tool_name not in ALLOWED_TOOLS:
        return json.dumps({"status": "error", "message": f"Tool '{tool_name}' is not allowed."})
    if not shutil.which(tool_name):
        return json.dumps({"status": "unavailable", "message": f"{tool_name} is not on PATH. Install that specific tool or check its executable name."})
    combined = f"{tool_name} {argument_string}"
    if not is_command_safe(combined):
        return json.dumps({"status": "error", "message": "Destructive sequence blacklisted."})
    try:
        safe_args = shlex.split(argument_string)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
    try:
        execution = subprocess.run(ALLOWED_TOOLS[tool_name] + safe_args, capture_output=True, text=True, timeout=timeout)
        return json.dumps({"status": "completed" if execution.returncode == 0 else "warning", "exit_code": execution.returncode, "stdout": execution.stdout.strip(), "stderr": execution.stderr.strip()}, indent=2)
    except Exception as e:
        return json.dumps({"status": "exception", "message": str(e)}, indent=2)

def open_app(app_name: str) -> str:
    aliases = {"vscode": "code", "vs code": "code", "chrome": "google-chrome"}
    executable = shutil.which(aliases.get(app_name.lower(), app_name))
    if not executable:
        return f"Application not found: {app_name}"
    process = subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return f"Launch requested for {app_name} (PID {process.pid})."

def run_terminal(command: str, background: bool = False, timeout: int | None = None) -> str:
    timeout = config.TOOL_TIMEOUT if timeout is None else timeout
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command must be a nonempty string")
    if not is_command_safe(command):
        raise UnsafeCommandError("Command matches a destructive-command pattern.")
    if background:
        process = subprocess.Popen(command, shell=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return f"Started background process {process.pid}; output is discarded."
    res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
    return json.dumps({"exit_code": res.returncode, "stdout": res.stdout[-12000:], "stderr": res.stderr[-12000:]})

def research(query: str, max_results: int = 5) -> str:
    from web_research import research as search
    return search(query, max_results)

def render_3d(model_data: dict) -> str:
    from viewer import render_scene
    return render_scene(model_data)


def list_skills() -> str:
    from diagnostics import skill_report
    return json.dumps(skill_report(), indent=2)


def installed_tool_names() -> list[str]:
    return sorted(name for name in ALLOWED_TOOLS if shutil.which(name))
