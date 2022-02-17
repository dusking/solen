import os
import csv
import json
import time
import logging
from typing import Dict
from pathlib import Path
from datetime import timedelta
from configparser import ConfigParser

import spl.token.instructions as spl_token
from solana.account import Account
from solana.rpc.commitment import *
from solana.rpc.api import Client
from solana.keypair import Keypair
from solana.rpc.types import TxOpts
from solana.publickey import PublicKey
from solana.rpc.core import RPCException
from solana.transaction import Transaction
from spl.token.client import Token
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import transfer_checked, TransferCheckedParams

from .response import *

logger = logging.getLogger("tiny_solana")


class TinySolana:
    def __init__(self, env):
        self.rpc = None
        self.token = None
        self.client = None
        self.config = None
        self.keypair = None
        self.account = None
        self.token_mint = None
        self.clock = time.monotonic
        self.run_start = self.clock()
        self.config_folder = Path.home().joinpath(".tiny")
        self.config_file = self.config_folder.joinpath("config.ini")
        self.load_config()
        self.init(env)

    def load_config(self):
        """
        Load configuration
        """
        self.config_folder.mkdir(parents=True, exist_ok=True)
        self.config = ConfigParser()
        self.config.read(str(self.config_file))

    def init(self, env: str):
        """
        Init members based on env
        """
        if env not in self.config["endpoint"]:
            valid_rpc_options = list(self.config["endpoint"].keys())
            logger.error(f"env {env} does not exists in config file. valid options: {valid_rpc_options}")
            raise Exception(f"missing env {env} in config")
        self.rpc = self.config["endpoint"][env]
        with open(os.path.expanduser(self.config["solana"]["keypair"])) as f:
            content = f.read()
            private_key = bytes(json.loads(content))
        self.account = Account(content[:32])
        self.keypair = Keypair.from_secret_key(private_key)
        self.client = Client(self.rpc, commitment=Confirmed)
        self.token_mint = self.config["addresses"]["token"]
        self.token = Token(self.client, PublicKey(self.token_mint), TOKEN_PROGRAM_ID, self.keypair)

    def set_start_time(self):
        self.run_start = self.clock()

    def elapsed_time(self):
        elapsed_time = self.clock() - self.run_start
        return str(timedelta(seconds=elapsed_time)).split(".")[0]

    def is_connected(self):
        return self.client.is_connected()

    def balance_sol(self, owner: str) -> int:
        """
        Returns the SOL amount for the given wallet address .
        """
        response = self.client.get_balance(PublicKey(owner))
        if "error" in response:
            error = response["error"]
            logger.error(f"failed to get token balance. error: {error}")
            return 0
        digits = 9
        lamport = response["result"]["value"]
        return lamport / pow(10, digits)

    def balance_token(self, owner: str) -> int:
        """
        Returns the token amount for the given wallet address .
        """
        response = self.token.get_balance(self.get_associated_address(owner, self.token_mint))
        if "error" in response:
            error = response["error"]
            logger.error(f"failed to get token balance. error: {error}")
            return 0
        return response["result"]["value"]['uiAmount']

    def get_associated_address(self, owner: str, token: str = None) -> PublicKey:
        """
        Derives the associated token address for the given wallet address and token mint.
        """
        token = token or self.token_mint
        return spl_token.get_associated_token_address(PublicKey(owner), PublicKey(token))

    def is_it_token_account(self, address: str) -> bool:
        info = self.client.get_account_info(address)
        return bool(info["result"]["value"] and str(info["result"]["value"]["owner"]) == str(TOKEN_PROGRAM_ID))

    def is_account_funded(self, address: str) -> bool:
        response = self.client.get_account_info(address)
        return response["result"]["value"] is not None

    def transfer_token(self, dest: str, amount: float, token: str = None, decimals: int = 9) -> Response:
        """
        Generate an instruction that transfers lamports from one account to another
        """        
        amount_lamport = int(amount * pow(10, 9))
        logger.info(f"going to transfer {amount} ({amount_lamport} lamport) from local wallet to {dest}")
        if not self.is_it_token_account(dest):
            dest_token_address = str(self.get_associated_address(dest))
            logger.info(f"recipient associated token account: {dest_token_address}")
            if not self.is_account_funded(dest_token_address):
                logger.info(f"create & fund recipient associated token account: {dest_token_address}")
                response = self.create_associated_token_account(dest)
                if response.err:
                    logger.error(f"failed to transfer token")
                    return Err(response)
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
                        signers=[])))
            options = TxOpts(skip_confirmation=False, preflight_commitment=Confirmed)
            response = self.client.send_transaction(transaction, self.keypair, opts=options)
            trn_sig = response["result"]
            logger.info(f"token been transferred, transaction signature: {trn_sig}")
            return Ok(trn_sig)
        except RPCException as ex:
            message = ex.args[0]["message"]
            logger.error(f"failed to transfer token. RPC error: {message}")
            return Err(f"{ex}")
        except Exception as ex:
            logger.error(f"failed to transfer token. error: {ex}")
            return Err(f"{ex}")

    def create_associated_token_account(self, owner: str) -> Response:
        """
        Create an associated token account.
        """
        try:
            return Ok(str(self.token.create_associated_token_account(PublicKey(owner))))
        except RPCException as ex:
            message = ex.args[0]["message"]
            logger.error(f"failed to create associate token account. RPC error: {message}")
            return Err(f"{ex}")
        except Exception as ex:
            logger.error(f"failed to create associate token account. error: {ex}")
            return Err(f"{ex}")

    def process_csv(self, csv_path: str) -> Dict:
        """
        Read the csv file and return dict of all the lines
        The keys are index since wallet may exist more than once
        """
        in_process_init = {}
        reader = csv.DictReader(open(csv_path))
        for i, row in enumerate(reader):
            in_process_init[i] = dict(
                wallet=row["wallet"],
                amount=row["amount"],
                finalized=False,
                signature="",
                error=""
            )
        return in_process_init

    def bulk_transfer_token(self, transfer_csv_path: str, in_process: bool = False):
        """
        Transfer token to multiple addresses, based on the content of transfer_csv_path
        If it's not the first run (running again for failure retry) need to run with in_process=True
        """
        logger.info(f"going to transfer tokens based on file: {transfer_csv_path}")
        file_extension = os.path.splitext(transfer_csv_path)[1]
        if file_extension != ".csv":
            logger.error(f"unsupported file type: {file_extension}. expecting csv")
            return
        if not os.path.exists(transfer_csv_path):
            logger.error(f"missing file: {transfer_csv_path}")
            return
        in_process_file = self.config_folder.joinpath(transfer_csv_path.replace(".csv", ".json"))
        if in_process_file.exists():
            if not in_process:
                logger.error(f"in process already exist: ({in_process_file}). indicate continue or delete file")
                return
        else:
            in_process_init = self.process_csv(transfer_csv_path)
            in_process_file.write_text(json.dumps(in_process_init))
        in_process = json.loads(in_process_file.read_text())
        total_items = len(in_process)
        left_items = sum(not i['signature'] for i in in_process.values())
        logger.info(f"going to handle {left_items} left to transfer, out of {total_items} transfer records")
        counter = 0
        for i, item in in_process.items():
            if item.get("signature"):
                continue
            counter += 1
            logger.info(f"[{i}] handle transfer {counter}/{left_items}, elapsed time: {self.elapsed_time()}")
            response = self.transfer_token(item["wallet"], float(item["amount"]))
            if response.err:
                in_process[i].update({"error": response.err})
            else:
                in_process[i].update({"signature": response.ok})
            in_process_file.write_text(json.dumps(in_process))
        logger.info("Done")

    def bulk_confirm_transactions(self, transfer_csv_path: str):
        """
        Verify that transfer amount transaction signatures are finalized
        """
        in_process_file = self.config_folder.joinpath(transfer_csv_path.replace(".csv", ".json"))
        if not in_process_file.exists():
            logger.error(f"missing in-process file: ({in_process_file})")
            return
        in_process = json.loads(in_process_file.read_text())
        total_items = len(in_process)
        left_items = sum(not i['finalized'] for i in in_process.values())
        logger.info(f"going to handle {left_items} left not verified, out of {total_items} records")
        for i, item in in_process.items():
            if not item.get("signature"):
                continue
            if item.get("finalized"):
                continue
            item = self.confirm_transaction(item["signature"])
            in_process[i].update({"finalized": item})
            in_process_file.write_text(json.dumps(in_process))
        logger.info("Done")

    def confirm_transaction(self, tx_sig: str, commitment: Commitment = Finalized, sleep_seconds: float = 1.0) -> bool:
        """
        Confirm the transaction identified by the specified signature.

        :param tx_sig: the transaction signature to confirm.
        :param commitment: Bank state to query. It can be either "finalized", "confirmed" or "processed".
        :param sleep_seconds: The number of seconds to sleep when polling the signature status.
        """
        timeout = time.time() + 30
        resp = {}
        last_confirmation_amount = 0
        max_retries = 60
        while max_retries and time.time() < timeout:
            max_retries -= 1
            resp = self.client.get_signature_statuses([tx_sig], search_transaction_history=True)
            maybe_rpc_error = resp.get("error")
            if maybe_rpc_error is not None:
                logger.error(f"Unable to confirm transaction {tx_sig}. {maybe_rpc_error}")
                return False
            resp_value = resp["result"]["value"][0]
            if resp_value is not None:
                confirmation_status = resp_value["confirmationStatus"]
                confirmation_rank = COMMITMENT_RANKS[confirmation_status]
                commitment_rank = COMMITMENT_RANKS[commitment]
                if confirmation_rank >= commitment_rank:
                    logger.info(f"transaction confirmed rank: {confirmation_rank}")
                    return True
                confirmation_amount = resp_value["confirmations"]
                if last_confirmation_amount != confirmation_amount:
                    logger.info(f"transaction confirmed by {confirmation_amount} validators")
                    last_confirmation_amount = confirmation_amount
            time.sleep(sleep_seconds)
        else:
            maybe_rpc_error = resp.get("error")
            logger.error(f"Unable to confirm transaction {tx_sig}. {maybe_rpc_error}")
            return False
