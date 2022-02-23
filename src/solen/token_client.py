import os
import csv
import json
import time
import logging
from typing import Dict, List, Union, Optional
from pathlib import Path
from datetime import timedelta
from functools import partial

import requests
import spl.token.instructions as spl_token
from asyncit.dicts import DotDict
from solana.rpc.core import RPCException, UnconfirmedTxError
from solana.publickey import PublicKey
from solana.rpc.types import TxOpts
from spl.token.client import Token
from solana.transaction import Transaction
from spl.token.constants import TOKEN_PROGRAM_ID
from solana.rpc.commitment import COMMITMENT_RANKS, Confirmed, Finalized, Commitment
from spl.token.instructions import TransferCheckedParams, transfer_checked

from .context import Context
from .response import Ok, Err, Response

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
        self.context = context or Context(env)
        self.client = self.context.client
        self.keypair = self.context.keypair
        self.token_mint = token_mint or self.context.configured_token_mint
        self.clock_time = time.perf_counter
        self.run_start = self.clock_time()
        self.config_folder = Path.home().joinpath(".config/solen")
        self.token = Token(self.client, PublicKey(self.token_mint), TOKEN_PROGRAM_ID, self.keypair)
        self.token_decimals = self.get_token_decimals()

    def _set_start_time(self):
        self.run_start = self.clock_time()

    def _elapsed_time(self):
        elapsed_time = self.clock_time() - self.run_start
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
        for token in tokens:
            if filter_key == "tags":
                if str(filter_value.upper()) in [str(v.upper()) for v in token.get(filter_key, []) if v]:
                    result.append(DotDict(token))
            elif token.get(filter_key, None) == filter_value:
                result.append(DotDict(token))
        return result

    def get_token_decimals(self, pubkey: Optional[Union[PublicKey, str]] = None) -> int:
        """Returns the decimal config of an SPL Token type. (default is the configured token)

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
        """Returns the token balance for the given wallet address. (default is keypair address)

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

    def get_associated_address(self, owner: str, token: str = None) -> PublicKey:
        """Derives the associated token address for the given wallet address and token mint."""
        token = token or self.token_mint
        return spl_token.get_associated_token_address(PublicKey(owner), PublicKey(token))

    def is_it_token_account(self, address: str) -> bool:
        info = self.client.get_account_info(address)
        return bool(info["result"]["value"] and str(info["result"]["value"]["owner"]) == str(TOKEN_PROGRAM_ID))

    def is_account_funded(self, address: str) -> bool:
        response = self.client.get_account_info(address)
        return response["result"]["value"] is not None

    def transfer_token(
        self, dest: str, amount: float, token: str = None, decimals: int = None, dry_run: bool = False
    ) -> Response:
        """Generate an instruction that transfers lamports from one account to another."""
        decimals = decimals or self.token_decimals
        amount_lamport = int(amount * pow(10, self.token_decimals))
        logger.info(f"going to transfer {amount} ({amount_lamport} lamport) from local wallet to {dest}")
        if dry_run:
            return Ok("test-run")
        if not self.is_it_token_account(dest):
            dest_token_address = str(self.get_associated_address(dest))
            logger.info(f"recipient associated token account: {dest_token_address}")
            if not self.is_account_funded(dest_token_address):
                logger.info(f"create & fund recipient associated token account: {dest_token_address}")
                response = self.create_associated_token_account(dest)
                if response.err:
                    logger.error("failed to transfer token (failed to create associated token account)")
                    return response
            dest = dest_token_address
        token = token or self.token_mint
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
            options = TxOpts(skip_confirmation=False, preflight_commitment=Confirmed)
            response = self.client.send_transaction(transaction, self.keypair, opts=options)
            trn_sig = response["result"]
            logger.info(f"token been transferred, transaction signature: {trn_sig}")
            return Ok(trn_sig)
        except RPCException as ex:
            message = dict(ex.args[0])["message"]
            logger.error(f"failed to transfer token. RPC error: {message}")
            return Err(f"{ex}")
        except Exception as ex:
            logger.error(f"failed to transfer token. error: {ex}")
            return Err(f"{ex}")

    def create_associated_token_account(self, owner: str) -> Response:
        """Create an associated token account."""
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

    def process_csv(self, csv_path: str) -> Dict:
        """Read the csv file and return dict of all the lines.
        The keys are index since wallet may exist more than once.
        """
        in_process_init = {}
        with open_utf8(csv_path) as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                in_process_init[i] = dict(
                    wallet=row["wallet"], amount=row["amount"].replace(",", ""), finalized=False, signature="", error=""
                )
        return in_process_init

    def bulk_transfer_token_init(self, transfer_csv_path: str):
        """Create the bulk transfer config based on given CSV file."""
        logger.info(f"going to create transfer config file based on file: {transfer_csv_path}")
        file_extension = os.path.splitext(transfer_csv_path)[1]
        if file_extension != ".csv":
            logger.error(f"unsupported file type: {file_extension}. expecting csv")
            return
        if not os.path.exists(transfer_csv_path):
            logger.error(f"missing file: {transfer_csv_path}")
            return
        in_process_file = self.config_folder.joinpath(transfer_csv_path.replace(".csv", ".json"))
        if in_process_file.exists():
            in_process = json.loads(in_process_file.read_text(encoding="utf-8"))
            left_items = sum(not i["signature"] for i in in_process.values())
            total_to_transfer = sum(float(i["amount"]) for i in in_process.values() if not i["signature"])
            total_to_transfer_str = f"{total_to_transfer:,}"
            logger.warning(
                f"transfer config file already exist: {in_process_file}. "
                f"left records: {left_items}, left to transfer: {total_to_transfer_str}"
            )
            return
        in_process_init = self.process_csv(transfer_csv_path)
        in_process_file.write_text(json.dumps(in_process_init), encoding="utf-8")
        in_process = json.loads(in_process_file.read_text(encoding="utf-8"))
        total_to_transfer = sum(float(i["amount"]) for i in in_process.values())
        total_to_transfer_str = f"{total_to_transfer:,}"
        logger.info(
            f"transfer config file been created: {in_process_file} "
            f"(total records: {len(in_process)}, total to transfer: {total_to_transfer_str})"
        )

    def bulk_transfer_token(self, transfer_csv_path: str, dry_run=False):
        """Transfer token to multiple addresses, based on the content of transfer_csv_path."""
        logger.info(f"going to transfer tokens based on file: {transfer_csv_path}")
        file_extension = os.path.splitext(transfer_csv_path)[1]
        if file_extension != ".csv":
            logger.error(f"unsupported file type: {file_extension}. expecting csv")
            return
        if not os.path.exists(transfer_csv_path):
            logger.error(f"missing file: {transfer_csv_path}")
            return
        in_process_file = self.config_folder.joinpath(transfer_csv_path.replace(".csv", ".json"))
        if not in_process_file.exists():
            logger.error(
                f"missing transfer config file: ({in_process_file}). run bulk-transfer init command to create it"
            )
            return
        in_process = json.loads(in_process_file.read_text(encoding="utf-8"))
        total_items = len(in_process)
        left_items = sum(not i["signature"] for i in in_process.values())
        logger.info(f"going to handle {left_items} left to transfer, out of {total_items} transfer records")
        counter = 0
        for i, item in in_process.items():
            if item.get("signature"):
                continue
            counter += 1
            current_token_balance = "N/A in dry-run" if dry_run else f"{self.balance(self.keypair.public_key):,}"
            logger.info(
                f"[{i}] [{self._elapsed_time()}] handle transfer {counter}/{left_items}, current balance: "
                f"{current_token_balance}"
            )
            response = self.transfer_token(item["wallet"], float(item["amount"]), dry_run=dry_run)
            if dry_run:
                continue
            if response.err:
                in_process[i].update({"error": response.err})
                if "Node is behind by" in response.err:
                    # When this error occurs (like "RPC error: Node is behind by 169 slots")
                    # it'll take at least a sec to start working again. keep trying will keep failing
                    time.sleep(1)
            else:
                in_process[i].update({"signature": response.ok, "error": ""})
            in_process_file.write_text(json.dumps(in_process), encoding="utf-8")
        total_transferred = sum(float(i["amount"]) for i in in_process.values() if i["signature"])
        total_not_transferred = sum(float(i["amount"]) for i in in_process.values() if not i["signature"])
        total_transferred_str = f"{total_transferred:,}"
        total_not_transferred_str = f"{total_not_transferred:,}"
        logger.info(
            f"Done. total transferred: {total_transferred_str}, total not transferred: {total_not_transferred_str} "
            f"(unverified)"
        )

    def bulk_confirm_transactions(self, transfer_csv_path: str):
        """Verify that transfer amount transaction signatures are finalized."""
        in_process_file = self.config_folder.joinpath(transfer_csv_path.replace(".csv", ".json"))
        if not in_process_file.exists():
            logger.error(f"missing in-process file: ({in_process_file})")
            return
        in_process = json.loads(in_process_file.read_text(encoding="utf-8"))
        total_items = len(in_process)
        left_items = sum(not i["finalized"] for i in in_process.values())
        logger.info(f"going to handle {left_items} left not verified, out of {total_items} records")
        for i, item in in_process.items():
            if not item.get("signature"):
                continue
            if item.get("finalized"):
                continue
            item = self.confirm_transaction(item["signature"])
            in_process[i].update({"finalized": item})
            in_process_file.write_text(json.dumps(in_process), encoding="utf-8")
        total_finalized = sum(i["finalized"] for i in in_process.values())
        logger.info(f"Done. total finalized: {total_finalized} / {len(in_process)}")

    def confirm_transaction(self, tx_sig: str, commitment: Commitment = Finalized, sleep_seconds: float = 1.0) -> bool:
        """Confirm the transaction identified by the specified signature.

        :param tx_sig: the transaction signature to confirm.
        :param commitment: Bank state to query. It can be either "finalized", "confirmed" or "processed".
        :param sleep_seconds: The number of seconds to sleep when polling the signature status.
        """
        timeout = time.time() + 30
        resp = {}
        last_confirmation_amount = 0
        max_retries = 60
        confirmed = False
        while max_retries and time.time() < timeout:
            max_retries -= 1
            resp = self.client.get_signature_statuses([tx_sig], search_transaction_history=True)
            maybe_rpc_error = resp.get("error")
            if maybe_rpc_error is not None:
                logger.error(f"Unable to confirm transaction {tx_sig}. {maybe_rpc_error}")
                break
            resp_value = resp["result"]["value"][0]
            if resp_value is not None:
                confirmation_status = resp_value["confirmationStatus"]
                confirmation_rank = COMMITMENT_RANKS[confirmation_status]
                commitment_rank = COMMITMENT_RANKS[commitment]
                if confirmation_rank >= commitment_rank:
                    logger.info(f"transaction confirmed rank: {confirmation_rank}")
                    confirmed = True
                    break
                confirmation_amount = resp_value["confirmations"]
                if last_confirmation_amount != confirmation_amount:
                    logger.info(f"transaction confirmed by {confirmation_amount} validators")
                    last_confirmation_amount = confirmation_amount
            time.sleep(sleep_seconds)
        else:
            maybe_rpc_error = resp.get("error")
            logger.error(f"Unable to confirm transaction {tx_sig}. {maybe_rpc_error}")
        return confirmed
