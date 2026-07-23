"""Allow ``python -m elyra`` invocation."""
from elyra import main
import sys

if __name__ == "__main__":
    sys.exit(main())
