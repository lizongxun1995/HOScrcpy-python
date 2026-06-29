"""Extract scrcpy server binaries from the SDK JAR."""
import zipfile
import os


def extract_servers(jar_path: str = None, dest_dir: str = None):
    """Extract scrcpy server ELF binaries from a hosScrcpy JAR."""
    if jar_path is None:
        jar_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "HOScrcpy-main", "HOScrcpy", "libs", "hosScrcpy-1.0.15-beta.jar",
        )
    if dest_dir is None:
        dest_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrcpy_server")

    os.makedirs(dest_dir, exist_ok=True)
    z = zipfile.ZipFile(jar_path)
    for name in z.namelist():
        if "libscrcpy/libscrcpy_server" in name:
            fname = os.path.basename(name)
            data = z.read(name)
            path = os.path.join(dest_dir, fname)
            with open(path, "wb") as f:
                f.write(data)
            is_elf = data[:4] == b"\x7fELF"
            print(f"  {fname}: {len(data):>10} bytes  ELF={is_elf}")
    print(f"\nExtracted {len(os.listdir(dest_dir))} binaries to {dest_dir}/")


if __name__ == "__main__":
    extract_servers()
