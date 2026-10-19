#!/usr/bin/env python3
"""
Model Widget — شريط عائم صغير فوق الشاشة.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from widget import ModelWidget


def main():
    app = ModelWidget()
    app.run()


if __name__ == "__main__":
    main()
