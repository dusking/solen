import os
import json
import time
import logging
from typing import Dict, List, Union, Optional
from datetime import timedelta
from functools import partial
from collections import Counter

import requests
import spl.token.instructions as spl_token
from asyncit.dicts import DotDict
from solana.rpc.api import MemcmpOpt
from solana.rpc.core import RPCException, UnconfirmedTxError
from solana.publickey import PublicKey
from solana.rpc.types import TxOpts
from spl.token.client import Token
from solana.transaction import Transaction
from spl.token.constants import TOKEN_PROGRAM_ID
from solana.rpc.commitment import Confirmed, Commitment
from spl.token.instructions import TransferCheckedParams, transfer_checked

from .context import Context
from .response import Ok, Err, Response
from .utils.bulk_handler import BulkHandler

logger = logging.getLogger(__name__)
open_utf8 = partial(open, encoding="UTF-8")


class TokenClient:  # pylint: disable=too-many-instance-attributes
    """Token Client class.

    :param env: The Solana env (options are based on the config file)
    :param token_mint: The token mint address, token commands will be based on that token.
        (default taken from the config file)

    The Solana RPC endpoint is taken from the config file - based on the given env parameter.
    For example, using the :ref:`config file <index:config file>`: in the example and "dev" parameter,
    the RPC endpoint will be: `https://api.devnet.solana.com`
    """

    def __init__(self, env: str, token_mint: str = None, context: Context = None):
        """Init Token Client."""
        self.env = env
        self.context = context or Context(self.env)
        self.client = self.context.client
        self.keypair = self.context.keypair
        self.config_folder = self.context.config_folder
        self.transfers_data_folder = self.config_folder.joinpath("transfers")
        self.bulk_transfer_token_handler = BulkHandler(
            self.client,
            self.env,
            self.transfers_data_folder,
            self.transfer_token,
            self.bulk_sum_info,
            "transfer",
            ["dest", "amount"],
        )
        self.token_mint = token_mint or self.context.configured_token_mint
        self.clock_time = time.perf_counter
        self.run_start = self.clock_time()
        self.token = Token(self.client, PublicKey(self.token_mint), TOKEN_PROGRAM_ID, self.keypair)
        self.token_decimals = self.get_token_decimals()
        os.makedirs(self.transfers_data_folder, exist_ok=True)

    def _set_start_time(self):
        self.run_start = self.clock_time()

    def _elapsed_time(self, run_start=None):
        run_start = run_start or self.run_start
        elapsed_time = self.clock_time() - run_start
        return str(timedelta(seconds=elapsed_time)).split(".", maxsplit=1)[0]

    def get_registered_info(self, **kwargs) -> List[Dict]:
        """return Solana registered token info.

        :param kwargs: filter param - can get only one filter option from the following:
           [address, symbol, name, tags] (Default is address of configured token).

        >>> from solen import TokenClient
        >>> token_client = TokenClient("main")
        >>> token_client.get_registered_info(symbol="TINY")
        """
        if len(kwargs) == 0:
            kwargs = {"address": self.token_mint}
        if len(kwargs) > 1:
            logger.error(f"can receive only one filter parameter, got {len(kwargs)}")
            return []
        if len(set(kwargs.keys()) - {"address", "symbol", "name", "tags"}):
            logger.error(f"got invalid filter: {list(kwargs.keys())}. Look at docs for valid options")
            return []
        filter_key, filter_value = list(kwargs.items())[0]
        solana_tokens = "https://raw.githubusercontent.com/solana-labs/token-list/main/src/tokens/solana.tokenlist.json"
        response = requests.get(solana_tokens)
        if response.status_code != 200:
            return []
        tokens = json.loads(response.content)["tokens"]
        result = []
        for token_info in tokens:
            if filter_key == "tags":
                if str(filter_value.upper()) in [str(v.upper()) for v in token_info.get(filter_key, []) if v]:
                    result.append(DotDict(token_info))
            elif token_info.get(filter_key, None) == filter_value:
                result.append(DotDict(token_info))
        return result

    def get_token_decimals(self, pubkey: Optional[Union[PublicKey, str]] = None) -> int:
        """Returns the decimal config of an SPL Token type. (default is the configured token)

        :param pubkey: The token mint address we want to get decimal info for (default is configured token).

        >>> from solen import TokenClient
        >>> token_client = TokenClient("dev")
        >>> token_client.get_token_decimals()
        """
        if pubkey:
            response = self.client.get_token_supply(str(pubkey), commitment=Confirmed)
            return response["result"]["value"]["decimals"]
        info = self.token.get_mint_info()
        return info.decimals

    def balance(self, owner: Optional[Union[PublicKey, str]] = None) -> int:
        """Returns the token balance for the given dest address. (default is keypair address)

        :param owner: The address that need to query for token balance (default is configured keypair address).

        >>> from solen import TokenClient
        >>> token_client = TokenClient("dev")
        >>> token_client.balance()
        """
        try:
            owner = owner or self.keypair.public_key
            response = self.token.get_balance(self.get_associated_address(owner, self.token_mint))
            if "error" in response:
                error = response["error"]
                logger.error(f"failed to retrieve token balance. error: {error}")
                return 0
            return response["result"]["value"]["uiAmount"]
        except RPCException as ex:
            message = dict(ex.args[0])["message"]
            logger.error(f"failed to retrieve balance. RPC error: {message}")
            return 0
        except Exception as ex:
            logger.error(f"failed to retrieve balance.. error: {ex}")
            return 0

    def get_associated_address(self, owner: str, token: Optional[str] = None) -> PublicKey:
        """Derives the associated token address for the given dest address and token mint.

        :param owner: The owner address that need to query for token associated address.
        :param token: The token need to query for associated address in the given address (default: configured token).
        """
        token = token or self.token_mint
        return spl_token.get_associated_token_address(PublicKey(owner), PublicKey(token))

    def is_it_token_account(self, address: str) -> bool:
        """Returns true if the given address is a token associate account.

        :param address: The address to query.
        """
        info = self.client.get_account_info(address)
        return bool(info["result"]["value"] and str(info["result"]["value"]["owner"]) == str(TOKEN_PROGRAM_ID))

    def is_account_funded(self, address: str) -> bool:
        """Return true id the given account exist and founded.

        :param address: The address to query.
        """
        response = self.client.get_account_info(address)
        return response["result"]["value"] is not None

    def transfer_token(
        self,
        dest: str,
        amount: float,
        dry_run: bool = False,
        skip_confirmation: bool = False,
        commitment: Commitment = Confirmed,
    ) -> Dict:
        """Generate an instruction that transfers amount of configured token from one self account to another.

        :param dest: Recipient address.
        :param amount: Amountof token to transfer.
        :param dry_run: If true the transfer will not be executed.
        :param skip_confirmation: If true send transfer will not be confirmed. It might be faster.
        :param commitment: The commitment type for send transfer.

        >>> from solen import TokenClient
        >>> from solana.rpc.commitment import Processed
        >>> token_client = TokenClient("dev")
        >>> token_client.transfer_token("Cy4y1XGR9pj7vFikWVGrdQAPWCChqV9gQHCLht6eXBLW", 0.01, True, Processed)
        """
        amount = float(amount)
        token = self.token_mint
        decimals = self.token_decimals
        run_start = self.clock_time()
        response = DotDict(dest=dest, amount=amount, confirmed=False, signature="")
        amount_lamport = int(amount * pow(10, self.token_decimals))
        logger.info(f"going to transfer {amount} ({amount_lamport} lamport) from local wallet to {dest}")
        if dry_run:
            return response.update(signature="test-run", ok=True, time=self._elapsed_time(run_start))
        if not self.is_it_token_account(dest):
            dest_token_address = str(self.get_associated_address(dest))
            logger.info(f"recipient associated token account: {dest_token_address}")
            if not self.is_account_funded(dest_token_address):
                logger.info(f"create & fund recipient associated token account: {dest_token_address}")
                create_associate_account_response = self.create_associated_token_account(dest)
                if create_associate_account_response.err:
                    err_msg = "failed to transfer token (failed to create associated token account)"
                    logger.error(err_msg)
                    return response.update(err=err_msg, ok=False, time=self._elapsed_time(run_start))
            dest = dest_token_address
        transaction = Transaction()
        try:
            transaction.add(
                transfer_checked(
                    TransferCheckedParams(
                        program_id=TOKEN_PROGRAM_ID,
                        source=self.get_associated_address(self.keypair.public_key, token),
                        mint=PublicKey(token),
                        dest=PublicKey(dest),
                        owner=self.keypair.public_key,
                        amount=amount_lamport,
                        decimals=decimals,
                        signers=[],
                    )
                )
            )
            options = TxOpts(skip_confirmation=skip_confirmation, preflight_commitment=commitment)
            send_transaction_response = self.client.send_transaction(transaction, self.keypair, opts=options)
            trn_sig = send_transaction_response["result"]
            logger.info(f"token been transferred, transaction signature: {trn_sig}")
            return response.update(signature=trn_sig, ok=True, time=self._elapsed_time(run_start))
        except RPCException as ex:
            message = dict(ex.args[0])["message"]
            logger.error(f"failed to transfer token. RPC error: {message}")
            return response.update(err=f"{ex}", ok=False, time=self._elapsed_time(run_start))
        except Exception as ex:
            logger.error(f"failed to transfer token. error: {ex}")
            return response.update(err=f"{ex}", ok=False, time=self._elapsed_time(run_start))

    def create_associated_token_account(self, owner: str) -> Response:
        """Create an associated token account

        :param owner: The address that need to create a token associated address for.
        """
        try:
            return Ok(str(self.token.create_associated_token_account(PublicKey(owner))))
        except RPCException as ex:
            message = dict(ex.args[0])["message"]
            logger.error(f"failed to create associate token account for {owner}. RPC error: {message}")
            return Err(f"{ex}")
        except UnconfirmedTxError as ex:
            message = ex.args[0]
            logger.error(f"failed to create associate token account for {owner}. UnconfirmedTx error: {message}")
            return Err(f"{message}")
        except Exception as ex:
            logger.error(f"failed to create associate token account. error: {ex}")
            return Err(f"failed to create associate token account for: {owner}")

    def bulk_transfer_token_init(self, csv_path: str):
        """Create the bulk transfer config based on given CSV file.

        :param csv_path: Path to a csv file in the format of: dest,amount.
        """
        in_process_data = self.bulk_transfer_token_handler.bulk_init(csv_path)
        logger.info(f"parsed {len(in_process_data)} lines of transfer commands")
        return len(in_process_data) > 0

    def bulk_sum_info(self, in_process: Dict = None, log_sum: bool = False):
        """Log sum status for token transfer

        :param in_process: Current content of the in-process json file (default taken from bulk_transfer_token_handler).
        :param log_sum: If true the sum data will be logged (not just returned).
        """
        in_process = in_process or self.bulk_transfer_token_handler.in_process

        total_items = len(in_process)
        total_amount_transferred = sum(float(i["amount"]) for i in in_process.values() if i["signature"])
        total_amount_transferred_str = f"{total_amount_transferred:,.4f}"
        total_items_with_no_signature = sum(not i["signature"] for i in in_process.values())
        items_with_signature_but_not_finalized = sum(not i["finalized"] for i in in_process.values() if i["signature"])
        total_not_confirmed_to_transfer = sum(float(i["amount"]) for i in in_process.values() if not i["finalized"])
        total_not_confirmed_to_transfer_str = f"{total_not_confirmed_to_transfer:,.4f}"
        total_to_transfer = sum(float(i["amount"]) for i in in_process.values())
        total_to_transfer_str = f"{total_to_transfer:,.4f}"
        total_amount_not_transferred = sum(float(i["amount"]) for i in in_process.values() if not i["signature"])
        total_amount_not_transferred_str = f"{total_amount_not_transferred:,.4f}"

        if log_sum:
            logger.info(
                f"Total transferred: {total_amount_transferred_str} out of {total_to_transfer_str}."
                f"left with amount of:  {total_amount_not_transferred_str} "
                f"({total_items_with_no_signature} / {total_items} items)"
            )

        return dict(
            total_items=total_items,
            items_with_no_signature=total_items_with_no_signature,
            items_with_signature_but_not_finalized=items_with_signature_but_not_finalized,
            total_to_transfer=total_to_transfer_str,
            total_amount_transferred=total_amount_transferred_str,
            left_unconfirmed_to_transfer=total_not_confirmed_to_transfer_str,
        )

    def bulk_transfer_token(
        self,
        csv_path: str,
        dry_run: bool = False,
        skip_confirm: bool = False,
        ignore_unfinalized_signature: bool = False,
    ):
        """Transfer token to multiple addresses, based on the content of transfer_csv_path.

        :param csv_path: Path to a csv file in the format of: dest,amount.
        :param dry_run: When true the transactions will be skipped.
        :param skip_confirm: When true transaction confirmation will be skipped. Run will be faster but less reliable.
        :param ignore_unfinalized_signature: When true actions with un-finalized transaction will retry processing.

        >>> from solen import TokenClient
        >>> token_client = TokenClient("main")
        >>> token_client.bulk_transfer_token(csv_path)
        when csv should contain transfer actions data, for example:
        dest,amount
        Cy4y1XGR9pj7vFikWVGrdQAPWCChqV9gQHCLht6eXBLW,0.001
        Cy4y1XGR9pj7vFikWVGrdQAPWCChqV9gQHCLht6eXBLW,0.001
        """
        transfer_response = self.bulk_transfer_token_handler.bulk_run(
            csv_path, dry_run, skip_confirm, ignore_unfinalized_signature
        )
        if not transfer_response.ok:
            logger.error(f"failed to transfer, err: {transfer_response.err}")
        return self.bulk_transfer_token_handler.sum_info()

    def bulk_confirm_transactions(self, csv_path: str):
        """Verify that transfer amount transaction signatures are finalized.

        :param csv_path: Path to the csv file that been processed.
        """
        self.bulk_transfer_token_handler.bulk_confirm(csv_path)

    def get_transfer_status(self, csv_path: str):
        """Get transfer status for a given transfer csv file.

        :param csv_path: Path to a csv file to retrieve transfer data for.
        """
        return self.bulk_transfer_token_handler.bulk_status(csv_path)

    def snapshot(self, token_mint: Optional[str] = None):
        """Get snapshot of token holders for a given token.

        :param token_mint: Token mint to get snapshot for (default: configured token).
        """
        token_mint = token_mint or self.token_mint
        memcmp_opts = [MemcmpOpt(offset=0, bytes=token_mint)]
        result = self.client.get_program_accounts(
            pubkey=TOKEN_PROGRAM_ID, encoding="jsonParsed", data_size=165, memcmp_opts=memcmp_opts
        )

        # extract owner to quantity dict
        holders = Counter()
        for data in result["result"]:
            owner = data["account"]["data"]["parsed"]["info"]["owner"]
            amount = data["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]
            holders[owner] += amount

        # sort
        items = list(holders.items())
        items.sort(key=lambda x: x[1], reverse=True)

        return items
