import logging
from functools import partial

from solana.publickey import PublicKey

from .context import Context

logger = logging.getLogger("solen")
open_utf8 = partial(open, encoding="UTF-8")


class SOLClient:  # pylint: disable=too-many-instance-attributes
    """SOL client class.

    :param env: The Solana env (options are based on the config file)

    The Solana RPC endpoint is taken from the config file - based on the given env parameter.
    For example, using the :ref:`config file <index:config file>`: in the example and "dev" parameter,
    the RPC endpoint will be: `https://api.devnet.solana.com`
    """

    def __init__(self, env: str, context: Context = None):
        """Init Token Client."""
        self.context = context or Context(env)
        self.client = self.context.client

    def balance(self, owner: str = None) -> int:
        """Returns the SOL amount for the given wallet address

        >>> from solen import SOLClient
        >>> sol_client = SOLClient("main")
        >>> sol_client.balance()
        """
        owner = owner or self.context.keypair.public_key
        response = self.client.get_balance(PublicKey(owner))
        if "error" in response:
            error = response["error"]
            logger.error(f"failed to get token balance. error: {error}")
            return 0
        digits = 9
        lamport = response["result"]["value"]
        return lamport / pow(10, digits)
