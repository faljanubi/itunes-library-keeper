# Double-click (or use the Start Menu shortcut) to launch without a console window.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toolkit.__main__ import main
main()
