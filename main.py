"""OverBlaster by OverLord Labs.

    python main.py            # run in the simulator
    python main.py deploy     # deploy to the glasses (needs RAVEN_APP_ID / RAVEN_APP_KEY)

Set OVERBLASTER_SIM=1 in the simulator: the arrow keys then steer your head and Space fires,
because the simulator can't fake a gyroscope or a microphone.
"""

import os

from raven_framework import RunApp

from overblaster.app import OverBlasterApp

if __name__ == "__main__":
    # Credentials stay out of the repo: empty values mean simulator mode.
    RunApp.run(
        lambda: OverBlasterApp(),
        app_id=os.environ.get("RAVEN_APP_ID", ""),
        app_key=os.environ.get("RAVEN_APP_KEY", ""),
    )
