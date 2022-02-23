import os
import json
import time
import logging
from typing import Optional
from pathlib import Path
from functools import partial

from solana.account import Account
from solana.keypair import Keypair
from solana.rpc.api import Client
from solana.rpc.commitment import COMMITMENT_RANKS, Confirmed, Finalized, Commitment

from .utils.config_parser import ConfigParser

logger = logging.getLogger("solen")
open_utf8 = partial(open, encoding="UTF-8")


class Context:  # pylint: disable=too-many-instance-attributes
    """Context class.

    :param env: The Solana env (options are based on the config file)

    The Solana RPC endpoint is taken from the config file - based on the given env parameter.
    For example, using the :ref:`config file <index:config file>`: in the example and "dev" parameter,
    the RPC endpoint will be:`https://api.devnet.solana.com`

    >>> from solen import Context
    >>> context = Context("dev")
    """

    def __init__(self, env: Optional[str] = None):
        """Init Solen Context."""
        self.env = env
        self.client = None
        self.config = None
        self.keypair = None
        self.account = None
        self.rpc_endpoint = None
        self.configured_token_mint = None
        self.clock_time = time.perf_counter
        self.run_start = self.clock_time()
        self.config_folder = Path.home().joinpath(".config/solen")
        self.config_file = self.config_folder.joinpath("config.ini")
        self.config = ConfigParser(str(self.config_file))
        self.config.load()
        self.init(env)
        logger.info(f"Solana client env: {self.env} - {self.rpc_endpoint}")

    def init(self, env: str):
        # pylint: disable=no-member
        """Init Solen instance based on env parameter."""
        self.env = env or self.config.solana.default_env
        if self.env not in self.config.endpoints:
            valid_rpc_options = list(self.config.endpoint.keys())
            logger.error(f"env {self.env} does not exists in config file. valid options: {valid_rpc_options}")
            raise Exception(f"missing env {self.env} in config")
        self.rpc_endpoint = self.config.endpoints.get(self.env)
        if not self.rpc_endpoint:
            raise Exception(f"missing env {self.env} in config file")
        with open_utf8(os.path.expanduser(self.config.solana.get(f"{self.env}_keypair"))) as f:
            content = f.read()
            private_key = bytes(json.loads(content))
        self.account = Account(content[:32])
        self.keypair = Keypair.from_secret_key(private_key)
        self.client = Client(self.rpc_endpoint, commitment=Confirmed)
        self.configured_token_mint = self.config.addresses.get(f"{self.env}_token")
        if not self.configured_token_mint:
            logger.warning(f"missing {self.env} token in config file")

    @property
    def my_address(self):
        return self.keypair.public_key

    def is_connected(self):
        return self.client.is_connected()
