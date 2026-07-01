import sys, socket, time
sys.path.insert(0, 'C:\\Users\\14057\\Documents\\AutoTestFramework\\HOScrcpy-python-api')
from hos_scrcpy.core.hdc_client import HdcClient

c = HdcClient()
c.execute('62Q0225B12006304', 'fport rm tcp:25556 tcp:8012', timeout=3)
r = c.execute('62Q0225B12006304', 'fport tcp:25556 tcp:8012', timeout=5)
print('fport:', repr(r))
time.sleep(1)
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(('127.0.0.1', 25556))
    print('Connected!')
    s.sendall(b'{"test":1}\n')
    data = s.recv(4096)
    print('Received:', data[:200])
except Exception as e:
    print('Connection failed:', e)
finally:
    s.close()
