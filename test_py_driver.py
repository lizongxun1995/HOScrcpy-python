import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hos_scrcpy.bridge.py_driver import PyHmDriver
print('PyHmDriver OK')
d = PyHmDriver('test')
for m in ['start', 'stop', 'start_capture', 'touch_down', 'touch_up', 'touch_move']:
    print(f'  {m}: {hasattr(d, m)}')
from demo.app import DemoApp
print('DemoApp OK')
print(f'  _on_connect_ok: {hasattr(DemoApp, "_on_connect_ok")}')
print(f'  _disconnect: {hasattr(DemoApp, "_disconnect")}')
