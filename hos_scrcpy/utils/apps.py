"""App management utilities — start, stop, list, info for HarmonyOS apps.

Mirrors uiautomator2's d.app_start/stop/list/info API.
"""

from hos_scrcpy.core.device import Device
from hos_scrcpy.utils.logger import logger

TAG = "Apps"


def app_start(device: Device, bundle_name: str, ability_name: str = "EntryAbility") -> str:
    """Launch an app on the device.

    Args:
        device: Device instance.
        bundle_name: App bundle name (e.g. 'com.example.app').
        ability_name: Entry ability name (default 'EntryAbility').

    Returns:
        Shell output string.

    Example:
        app_start(dev, "com.ohos.settings")
    """
    cmd = f"aa start -a {ability_name} -b {bundle_name}"
    logger.debug(f"{TAG}: start {bundle_name}/{ability_name}")
    return device.execute_shell(cmd, timeout=10)


def app_stop(device: Device, bundle_name: str) -> str:
    """Force-stop an app on the device.

    Args:
        device: Device instance.
        bundle_name: App bundle name.

    Returns:
        Shell output string.
    """
    cmd = f"aa force-stop {bundle_name}"
    logger.debug(f"{TAG}: stop {bundle_name}")
    return device.execute_shell(cmd, timeout=10)


def app_list(device: Device) -> list[str]:
    """List installed third-party app bundle names.

    Returns:
        List of bundle name strings.
    """
    output = device.execute_shell("bm dump -a", timeout=10)
    if not output:
        return []
    bundles = []
    for line in output.splitlines():
        line = line.strip()
        if line and not line.startswith("ErrorMessage"):
            bundles.append(line)
    return bundles


def app_info(device: Device, bundle_name: str) -> dict | None:
    """Get info about an installed app.

    Returns:
        Dict with bundle_name, or None if not found.
    """
    output = device.execute_shell(f"bm dump -n {bundle_name}", timeout=10)
    if not output or "not found" in output.lower():
        return None
    return {"bundle_name": bundle_name, "raw": output}


def screen_on(device: Device) -> bool:
    """Turn the screen on (idempotent — does nothing if already on).

    Returns True if action was taken.
    """
    # Check current screen state by trying to take a screenshot
    # If the screen is off, power key toggles it on
    # HarmonyOS doesn't have a direct screen-state query,
    # so we check via display info
    result = device.execute_shell(
        "hidumper -s 4608 -a display", timeout=5
    )
    if result and "PowerState=ON" in result:
        return False
    device.press_key(26)  # KEYCODE_POWER
    return True


def screen_off(device: Device) -> bool:
    """Turn the screen off (idempotent — does nothing if already off).

    Returns True if action was taken.
    """
    result = device.execute_shell(
        "hidumper -s 4608 -a display", timeout=5
    )
    if result and "PowerState=OFF" in result:
        return False
    device.press_key(26)  # KEYCODE_POWER
    return True


def device_info(device: Device) -> dict:
    """Get device information dict.

    Returns dict with keys: sn, model, os_version, screen_size, sdk_version.
    """
    info = {"sn": device.sn, "ip": device.ip}
    try:
        output = device.execute_shell("param get const.product.model", timeout=5)
        info["model"] = output.strip() if output else "unknown"
    except Exception:
        info["model"] = "unknown"
    try:
        output = device.execute_shell("param get const.ohos.fullname", timeout=5)
        info["os_version"] = output.strip() if output else "unknown"
    except Exception:
        info["os_version"] = "unknown"
    try:
        output = device.execute_shell("param get const.ohos.apiversion", timeout=5)
        info["sdk_version"] = output.strip() if output else "unknown"
    except Exception:
        info["sdk_version"] = "unknown"
    return info


def push(device: Device, local_path: str, remote_path: str) -> bool:
    """Push a file to the device.

    Returns True on success.
    """
    result = device.execute(
        f'file send "{local_path}" "{remote_path}"', timeout=30
    )
    return "finish" in result.lower() or "FileTransfer" in result


def pull(device: Device, remote_path: str, local_path: str) -> bool:
    """Pull a file from the device.

    Returns True on success.
    """
    result = device.execute(
        f'file recv "{remote_path}" "{local_path}"', timeout=30
    )
    return "finish" in result.lower() or "FileTransfer" in result
