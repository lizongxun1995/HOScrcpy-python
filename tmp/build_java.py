import subprocess, glob, os

base = r'C:\Users\14057\Documents\AutoTestFramework\HOScrcpy-python-api'
javac = r'C:\Program Files\Microsoft\jdk-25.0.3.9-hotspot\bin\javac.exe'
src = base + os.sep + r'hos_scrcpy\bridge\StreamBridge.java'
out = base + os.sep + r'hos_scrcpy\bridge'
libs = base + os.sep + r'HOScrcpy-main\HOScrcpy\libs'
cp = ';'.join(glob.glob(os.path.join(glob.escape(libs), '*.jar')))

cmd = f'"{javac}" -cp "{cp}" -d "{out}" "{src}"'
print('CMD:', cmd[:200])
r = subprocess.run(cmd, capture_output=True, text=True, shell=True)
print('STDOUT:', r.stdout[:500])
print('STDERR:', r.stderr[:500])
print('EXIT:', r.returncode)
