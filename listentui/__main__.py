#!/usr/bin/env python3

import sys

if __package__ is None and not getattr(sys, 'frozen', False):  # type: ignore
    # direct call of __main__.py
    import os.path
    path = os.path.realpath(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))

from listentui.main import main

if __name__ == '__main__':
    main()
