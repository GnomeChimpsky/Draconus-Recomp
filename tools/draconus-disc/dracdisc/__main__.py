"""Allow ``python -m dracdisc`` from the tool directory."""

from .cli import main

raise SystemExit(main())
