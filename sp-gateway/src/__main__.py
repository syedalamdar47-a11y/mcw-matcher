"""Entry point: `python -m src`

This exists so that runner.py is only ever imported as `src.runner`, never as
`__main__`. Running `python -m src.runner` directly would load the module twice
under two names — once as `__main__` and once as `src.runner` when a feed does
`from ..runner import feed` — giving two separate feed registries, one of which
is always empty. The symptom is a scheduler that starts cleanly and runs nothing.
"""

from .runner import main

raise SystemExit(main())
