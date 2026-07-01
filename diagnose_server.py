"""推送 scrcpy server ELF 到设备并运行诊断"""
import subprocess, os, time

base = r'C:\Users\14057\Documents\AutoTestFramework\HOScrcpy-python-api'
server_dir = base + r'\hos_scrcpy\bridge\scrcpy_server'
hdc = base + r'\hos_scrcpy\toolchains\hdc.exe'
sn = '62Q0225B12006304'

# 1. 检查设备上已有的 server 文件
print("=== 设备上现有的 scrcpy server ===")
r = subprocess.run(
    [hdc, '-t', sn, 'shell', 'ls -la /data/local/tmp/libscrcpy* /data/local/tmp/libscreen* 2>&1'],
    capture_output=True, text=True, timeout=10)
print(r.stdout[:1000])
print(r.stderr[:200])

# 2. 推送未推送的 server 文件
print("\n=== 推送 server 文件 ===")
for name in sorted(os.listdir(server_dir)):
    if not name.endswith('.z.so'):
        continue
    remote_path = f'/data/local/tmp/{name}'
    # 检查是否已存在
    check = subprocess.run(
        [hdc, '-t', sn, 'shell', f'ls -la {remote_path} 2>/dev/null && echo EXISTS || echo NOT_EXISTS'],
        capture_output=True, text=True, timeout=5)
    if 'EXISTS' in check.stdout:
        print(f'  {name}: already exists')
        continue
    
    local = os.path.join(server_dir, name)
    print(f'  {name}: pushing...', end=' ')
    r = subprocess.run(
        [hdc, '-t', sn, 'file', 'send', local, remote_path],
        capture_output=True, text=True, timeout=30)
    print('OK' if r.returncode == 0 else f'FAIL: {r.stderr[:100]}')

# 3. 运行 server, 捕获错误
print("\n=== 运行 server 诊断 ===")
for name in [
    'libscrcpy_server_unix_6.5-20260313.z.so',  # SDK 自动选择
    'libscrcpy_server0.z.so',                   # 通用版
    'libscrcpy_server_5.10-20260114.z.so',      # 旧内核
    'libscrcpy_server_unix_6.4-20260113.z.so',  # 6.4 内核
    'libscrcpy_server_unix_6.3.1-20260113.z.so', # 6.3 内核
    'libscrcpy_server2.z.so',                    # 小体积变体
    'libscrcpy_server3.z.so',                    # 小体积变体
    'libscrcpy_server1.z.so',                    # 通用版2
    'libscrcpy_server_emulator.z.so',            # 模拟器
]:
    remote = f'/data/local/tmp/{name}'
    # chmod + 运行 4 秒后 kill
    cmd = (
        f'chmod 755 {remote} 2>/dev/null; '
        f'echo "=== START {name} ==="; '
        f'{remote} 2>&1; '
        f'echo "=== EXIT code=$? ==="'
    )
    r = subprocess.run(
        [hdc, '-t', sn, 'shell', cmd],
        capture_output=True, text=True, timeout=8)
    out = r.stdout.strip()
    if 'START' in out:
        # 提取 START 到 EXIT 之间的内容
        lines = out.splitlines()
        start_idx = next(i for i, l in enumerate(lines) if 'START' in l)
        end_idx = next((i for i, l in enumerate(lines) if 'EXIT' in l), len(lines))
        result = '\n'.join(lines[start_idx:end_idx+1])
        print(f'\n{name}:')
        print(f'  {result[:300]}')
    else:
        print(f'\n{name}: no output')
