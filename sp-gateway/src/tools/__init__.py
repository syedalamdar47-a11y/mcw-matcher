"""One-off, operator-run tools. They reuse the saved session cookies over httpx
and never open a browser or attempt a sign-in — if the session has expired
they stop, so they can never race the live scheduler for the single session.

Run on the gateway machine, e.g.:
    fly ssh console --app mcw-sp-gateway -C "python -m src.tools.discover_clients"
"""
