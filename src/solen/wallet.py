import logging

from .context import Context
from .token_client import TokenClient
from .nft_client import NFTClient
from .sol_client import SOLClient

logger = logging.getLogger("solen")


class Wallet:
    def __init__(self, env: str = None, context: Context = None):
        if env and context:
            logger.error("Wallet - Need to init with env or context - not both")
        if not env and not context:
            logger.error("Wallet - Need to init with env or context")
        self.context = context or Context(env)
        self.client = self.context.client
        self.mbs = TokenClient(context=self.context)
        self.sol = SOLClient(context=self.context)
        self.nft = NFTClient(context=self.context)
