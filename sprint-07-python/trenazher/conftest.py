import os
import sys

# чтобы `import zadachi` работал независимо от того, откуда запущен pytest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
