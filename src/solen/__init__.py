import sys

from .context import Context
from .version import __version__
from .nft_client import NFTClient
from .sol_client import SOLClient
from .token_client import TokenClient

if sys.version_info < (3, 7):
    raise EnvironmentError("Python 3.7 or above is required.")
