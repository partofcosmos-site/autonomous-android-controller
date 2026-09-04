#!/usr/bin/env python3
"""
God-Mode Android Daemon CLI Forwarder
Executes god_daemon.py from the parent directory or /sdcard/agent.
"""
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
parent = os.path.dirname(here)

if os.path.exists(os.path.join(parent, "god_daemon.py")):
    sys.path.insert(0, parent)
    import god_daemon
    if __name__ == "__main__":
        god_daemon.main()
elif os.path.exists("/sdcard/agent/god_daemon.py"):
    sys.path.insert(0, "/sdcard/agent")
    import god_daemon
    if __name__ == "__main__":
        god_daemon.main()
else:
    print("[-] Error: god_daemon.py not found in parent or /sdcard/agent.")
    sys.exit(1)
