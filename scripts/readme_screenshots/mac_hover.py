"""Send pointer moves to one app (not the real pointer) to reveal hover controls.

mac_hover.py PID X Y
"""

import sys
import time

import Quartz

pid = int(sys.argv[1])
x = float(sys.argv[2])
y = float(sys.argv[3])
for dx in (0, 6, 12, 18):
    e = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, (x + dx, y), Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPostToPid(pid, e)
    time.sleep(0.08)
