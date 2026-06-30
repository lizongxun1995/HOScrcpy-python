"""Subprocess executor with timeout — mirrors Java ProcessExecutor.

Accepts command as a list of args (preferred, shell=False) for safety,
or as a string (shell=True, deprecated).
"""

import shlex
import subprocess
import threading
from hos_scrcpy.utils.logger import logger


def run(cmd: list[str] | str, timeout: int = 10, cwd: str = None) -> tuple[str, int]:
    """Execute a command with timeout and return (output, returncode).

    Args:
        cmd: Command as a list of args (recommended, shell=False).
             Accepts a plain string too (shell=True, deprecated).
        timeout: Timeout in seconds before process is killed.
        cwd: Optional working directory.

    Returns:
        Tuple of (combined stdout+stderr string, process return code).
        Return code -1 means the process could not be started at all.
    """
    output = []
    returncode = -1

    if isinstance(cmd, str):
        # String form — uses shell=True (legacy path)
        args_for_popen: list[str] | str = cmd
        use_shell = True
    else:
        args_for_popen = cmd
        use_shell = False

    try:
        proc = subprocess.Popen(
            args_for_popen,
            shell=use_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
        )

        def read_stream(stream, label: str = ""):
            try:
                for line in iter(stream.readline, b""):
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    output.append(f"{label}{decoded}")
            except Exception:
                pass

        stdout_thread = threading.Thread(target=read_stream, args=(proc.stdout, ""))
        stderr_thread = threading.Thread(target=read_stream, args=(proc.stderr, "ErrorMessage:"))

        stdout_thread.start()
        stderr_thread.start()

        try:
            proc.wait(timeout=timeout)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
            returncode = -1
            prefix = cmd if isinstance(cmd, str) else " ".join(cmd)
            logger.debug(f"Process timed out after {timeout}s: {prefix[:80]}...")

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

    except FileNotFoundError:
        return (f"ErrorMessage:command not found: {cmd[0] if isinstance(cmd, list) else cmd.split()[0]}", 127)
    except Exception as ex:
        logger.debug(f"Process execution error: {ex}")
        return (f"ErrorMessage:{ex}", -1)

    return ("\n".join(output), returncode)
