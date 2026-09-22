"""Extract scrcpy server binaries from the upstream SDK JAR.

No runtime dependency on the JAR — this is a maintenance tool for refreshing
the bundled so assets under bridge/scrcpy_server/ when a new device SDK
appears. Sources:

- libscrcpy/libscrcpy_server*.z.so  → video extension libraries (gRPC H.264)
- uitest_agent_*.so (jar root)      → touch agent libraries (uitest JSON socket)
"""
import zipfile
import os


def extract_servers(jar_path: str = None, dest_dir: str = None):
    """Extract scrcpy server and uitest agent ELF binaries from a hosScrcpy JAR."""
    if jar_path is None:
        jar_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "HOScrcpy-main", "hosScrcpy-1.0.18-beta.jar",
        )
    if dest_dir is None:
        dest_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrcpy_server")

    os.makedirs(dest_dir, exist_ok=True)
    z = zipfile.ZipFile(jar_path)
    for name in z.namelist():
        is_video = "libscrcpy/libscrcpy_server" in name
        is_agent = name.startswith("uitest_agent_") and name.endswith(".so")
        if not (is_video or is_agent):
            continue
        fname = os.path.basename(name)
        data = z.read(name)
        path = os.path.join(dest_dir, fname)
        with open(path, "wb") as f:
            f.write(data)
        is_elf = data[:4] == b"\x7fELF"
        print(f"  {fname}: {len(data):>10} bytes  ELF={is_elf}")
    print(f"\nExtracted binaries to {dest_dir}/")


if __name__ == "__main__":
    extract_servers()
