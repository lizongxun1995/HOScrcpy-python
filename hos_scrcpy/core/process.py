"""Subprocess executor with timeout — mirrors Java ProcessExecutor."""

import subprocess
import threading
from hos_scrcpy.utils.logger import logger


def run(cmd: str, timeout: int = 10, cwd: str = None) -> tuple[str, int]:
    """Execute a command with timeout and return (output, returncode).

    Args:
        cmd: Full command string to execute.
        timeout: Timeout in seconds before process is killed.
        cwd: Optional working directory.

    Returns:
        Tuple of (combined stdout+stderr string, process return code).
        Return code -1 means the process could not be started at all.
    """
    output = []
    returncode = -1

    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
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
            logger.debug(f"Process timed out after {timeout}s: {cmd[:80]}...")

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

    except FileNotFoundError:
        return (f"ErrorMessage:command not found: {cmd.split()[0]}", 127)
    except Exception as ex:
        logger.debug(f"Process execution error: {ex}")
        return (f"ErrorMessage:{ex}", -1)

    return ("\n".join(output), returncode)
