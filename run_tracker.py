# run_tracker.py
import sys
from tracker.Tracker import Tracker

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else None
    tracker = Tracker(symbol=symbol)
    tracker.run()
