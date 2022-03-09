import os
import json
import logging
from functools import partial

from asyncit.dicts import DotDict
from solana.keypair import Keypair
from solana.rpc.core import RPCException
from solana.publickey import PublicKey
from solana.transaction import Transaction
from solana.system_program import SYS_PROGRAM_ID, TransferParams, CreateAccountParams, transfer, create_account

from .context import Context
from .core.transactions import Transactions

logger = logging.getLogger("solen")
open_utf8 = partial(open, encoding="UTF-8")


class SOLClient:  # pylint: disable=too-many-instance-attributes
    """SOL client class.

    :param env: The Solana env (options are based on the config file)

    The Solana RPC endpoint is taken from the config file - based on the given env parameter.
    For example, using the :ref:`config file <index:config file>`: in the example and "dev" parameter,
    the RPC endpoint will be: `https://api.devnet.solana.com`
    """

    def __init__(self, env: str = None, context: Context = None):
        """Init Token Client."""
        if env and context:
            logger.error("SOLClient - Need to init with env or context - not both")
        if not env and not context:
            logger.error("SOLClient - Need to init with env or context")
        self.context = context or Context(env)
        self.client = self.context.client
        self.transaction = Transactions()

    @property
    def env(self):
        return self.context.env

    def create_account(self, save_to_file: bool = False, file_suffix: str = "") -> DotDict:
        """Create a new Solana account.

        :param save_to_file: Create private key file.
        :param file_suffix: Specify suffix to the new private key file.
        """
        key = Keypair()
        logger.info(f"Going to create a new account based on the new keypair of: {key.public_key}.")
        transaction = Transaction()
        transaction.add(
            create_account(
                CreateAccountParams(
                    from_pubkey=PublicKey(self.context.keypair.public_key),
                    new_account_pubkey=key.public_key,
                    lamports=self.context.client.get_minimum_balance_for_rent_exemption(88).get("result"),
                    space=88,
                    program_id=SYS_PROGRAM_ID,
                )
            )
        )
        end_tx = self.context.client.send_transaction(transaction, self.context.keypair, key)
        transaction_signature = end_tx["result"]
        logger.info(f"Create account {key.public_key} transaction: {transaction_signature}")
        if save_to_file:
            suffix = f"{self.env}.{file_suffix.strip('.')}" if file_suffix else f"{self.env}"
            filepath = os.path.expanduser(f"~/.config/solana/id.json.{str(key.public_key)[:10]}.{suffix}")
            with open_utf8(filepath, "w") as f:
                json.dump(list(key.secret_key), f)
            logger.info(f"New secret key save to: {filepath}")
        logger.info(f"waiting for transaction confirmation for: {transaction_signature}")
        confirm_response = self.transaction.await_confirmation(self.client, transaction_signature)
        return DotDict(ok=confirm_response, transaction=transaction_signature, public_key=key.public_key)

    def transfer(self, destination: str, amount: float) -> DotDict:
        """Transfer SOL to destination address.

        :param destination: Destination address to receive the SOL.
        :param amount: Amount to transfer.
        """
        sol_decimals = 9
        amount_lamport = int(amount * pow(10, sol_decimals))
        response = DotDict(dest=destination, amount=amount, amount_lamport=amount_lamport)
        try:
            txn = Transaction().add(
                transfer(
                    TransferParams(
                        from_pubkey=PublicKey(self.context.keypair.public_key),
                        to_pubkey=PublicKey(destination),
                        lamports=amount_lamport,
                    )
                )
            )
        except RPCException as ex:
            message = dict(ex.args[0])["message"]
            logger.error(f"failed to transfer SOL. RPC error: {message}")
            return response.update(err=f"{ex}", ok=False)
        except Exception as ex:
            logger.error(f"failed to transfer SOL. error: {ex}")
            return response.update(err=f"{ex}", ok=False)
        transaction = self.context.client.send_transaction(txn, self.context.keypair)
        transaction_signature = transaction["result"]
        logger.info(f"waiting for transaction confirmation for: {transaction_signature}")
        confirm_response = self.transaction.await_confirmation(self.client, transaction_signature, max_timeout=40)
        return response.update(ok=confirm_response, transaction=transaction_signature)

    def balance(self, owner: str = None) -> int:
        """Returns the SOL amount for the given wallet address

        :param owner: The address to get balance for (Default is configured keypair address).

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
