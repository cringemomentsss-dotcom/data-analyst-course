import os
import sys

import matplotlib
matplotlib.use("Agg")   # без окон: тесты идут в консоли

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
