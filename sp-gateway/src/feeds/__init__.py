"""Feed modules.

Importing this package populates the registry in runner.py, so every feed to be
scheduled must be imported here.

AVAILABILITY SOURCE — one owner at a time:
  * calendar.py (authed) is the PRIMARY source: the real SimplePractice calendar,
    reflecting blocked time, polled every 30s during business hours. It reports
    health under the feed name "clinician_availability", which is what the Matcher
    UI trusts.
  * availability.py (public, no login) is the FALLBACK. It is intentionally NOT
    registered while the calendar feed is the source, to avoid two writers
    fighting over the same rows. Re-enable it (import below) if the calendar feed
    is ever taken offline — it will resume writing within 10 minutes.
"""

from . import calendar  # noqa: F401  authed calendar — primary availability source
# from . import availability  # noqa: F401  public fallback — enable if calendar is offline
from . import client_check  # noqa: F401  nightly HubSpot-vs-SimplePractice check → FDO dashboard

__all__ = ["calendar", "client_check"]
