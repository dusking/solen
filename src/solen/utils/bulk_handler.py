import os
import csv
import json
import time
import logging
from typing import Dict, List, Union, Optional
from pathlib import Path
from datetime import timedelta
from functools import partial

from asyncit import Asyncit
from asyncit.dicts import DotDict
from solana.rpc.commitment import COMMITMENT_RANKS, Confirmed, Finalized, Processed, Commitment

logger = logging.getLogger(__name__)
open_utf8 = partial(open, encoding="UTF-8")


class BulkHandler:  # pylint: disable=too-many-instance-attributes
    """Handle class for bulk Solana actions."""

    def __init__(self, client, env, data_folder, action_callback, sum_info_callback, action_name, columns):
        self.client = client
        self.env = env
        self.clock_time = time.perf_counter
        self.data_folder = data_folder
        self.action = action_callback
        self.action_name = action_name
        self.sum_info = sum_info_callback
        self.run_start = self.clock_time()
        self.columns = columns
        self.in_process = {}
        if not self.env:
            raise ValueError("Missing env")

    def _set_start_time(self):
        self.run_start = self.clock_time()

    def _elapsed_time(self, run_start=None):
        run_start = run_start or self.run_start
        elapsed_time = self.clock_time() - run_start
        return str(timedelta(seconds=elapsed_time)).split(".", maxsplit=1)[0]

    def process_transfer_csv(self, csv_path: str) -> Dict:
        """Read the csv file and return dict of all the lines. The line index is the key.

        :param csv_path: Path to a csv file with the actions to perform.
        """
        in_process_init = {}
        with open_utf8(csv_path) as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                row_data = {}
                for column in self.columns:
                    row_data[column] = row[column].replace(",", "")
                row_data.update(finalized=False, signature="", error="")
                in_process_init[i] = row_data
        return in_process_init

    def _get_in_process_json_path(self, csv_path: str) -> Path:
        """Convert csv the path to the json config file path, in the solen config folder.

        :param csv_path: Path to a csv file with the actions to perform.
        """
        csv_name = os.path.basename(csv_path)
        csv_new_suffix = csv_name.replace(".csv", ".json")
        csv_with_prefix = f"{self.env}_{csv_new_suffix}"
        return self.data_folder.joinpath(csv_with_prefix)

    def bulk_init(self, csv_path: str) -> Dict:
        """Create the bulk process file based on given CSV file.

        :param csv_path: Path to a csv file with the actions to perform.
        """
        csv_path = os.path.expanduser(csv_path)
        file_extension = os.path.splitext(csv_path)[1]
        if file_extension != ".csv":
            logger.error(f"unsupported file type: {file_extension}. expecting csv")
            return {}
        if not os.path.exists(csv_path):
            logger.error(f"missing file: {csv_path}")
            return {}
        in_process_file = self._get_in_process_json_path(csv_path)
        if in_process_file.exists():
            logger.info(f"process config file: {in_process_file}")
            self.in_process = json.loads(in_process_file.read_text(encoding="utf-8"))
            self.sum_info(self.in_process, log_sum=True)
            return self.in_process
        logger.info(f"going to create bulk process file based on file: {csv_path}")
        in_process_init = self.process_transfer_csv(csv_path)
        in_process_file.write_text(json.dumps(in_process_init), encoding="utf-8")
        logger.info(f"process config file been created: {in_process_file}")
        self.in_process = json.loads(in_process_file.read_text(encoding="utf-8"))
        self.sum_info(self.in_process, log_sum=True)
        return self.in_process

    def bulk_run(self, csv_path: str, dry_run: bool = False, skip_confirm: bool = False):
        """Transfer token to multiple addresses, based on the content of transfer_csv_path.

        :param csv_path: Path to a csv file to process.
        :param dry_run: When true the transactions will be skipped.
        :param skip_confirm: When true transaction confirmation will be skipped. Run will be faster but less reliable.

        when csv should contain action data, that can be parsed by the actions function.
        """
        response = DotDict(csv_path=csv_path, dry_run=dry_run, skip_confirm=skip_confirm)
        csv_path = os.path.expanduser(csv_path)
        logger.info(f"going to run actions based on file: {csv_path} (dry_run: {dry_run})")
        run_start = self.clock_time()
        file_extension = os.path.splitext(csv_path)[1]
        if file_extension != ".csv":
            logger.error(f"unsupported file type: {file_extension}, expecting csv.")
            return response.update(ok=False, err=f"unsupported file type: {file_extension}, expecting csv.")
        if not os.path.exists(csv_path):
            logger.error(f"missing file: {csv_path}")
            return response.update(ok=False, err=f"missing file: {csv_path}")
        in_process_file = self._get_in_process_json_path(csv_path)
        if not in_process_file.exists():
            logger.error(f"missing json config file: ({in_process_file}). run bulk-transfer init command to create it")
            return response.update(ok=False, err=f"missing json config file: ({in_process_file}).")
        self.in_process = json.loads(in_process_file.read_text(encoding="utf-8"))
        total_items = len(self.in_process)
        left_items = sum(not i["signature"] for i in self.in_process.values())
        logger.info(f"going to handle {left_items} out of {total_items} actions")
        counter = 0
        for i, item in self.in_process.items():
            if item.get("signature"):
                continue
            counter += 1
            # current_token_balance = "N/A in dry-run" if dry_run else f"{self.balance(self.keypair.public_key):,}"
            logger.info(
                f"[{i}] [{self._elapsed_time()}] handle {self.action_name} {counter}/{left_items}, current balance: "
            )
            transfer_args = DotDict(dry_run=dry_run)
            for column in self.columns:
                transfer_args[column] = item[column]
            if skip_confirm:
                transfer_args.skip_confirmation = True
                transfer_args.commitment = Processed
            response = self.action(**transfer_args)
            if dry_run:
                continue
            if not response.ok:
                self.in_process[i].update({"error": response.err, "time": response.time})
                if "Node is behind by" in response.err:
                    # When this error occurs (like "RPC error: Node is behind by 169 slots")
                    # it'll take at least a sec to start working again. keep trying will keep failing
                    time.sleep(1)
            else:
                self.in_process[i].update({"signature": response.signature, "error": "", "time": response.time})
            in_process_file.write_text(json.dumps(self.in_process), encoding="utf-8")
        logger.info(f"Bulk run completed after {self._elapsed_time(run_start)}.")
        self.in_process = json.loads(in_process_file.read_text(encoding="utf-8"))
        return response.update(ok=True)

    def bulk_confirm(self, csv_path: str):
        """Verify that transfer amount transaction signatures are finalized.

        :param csv_path: Path to a csv file in the format of: wallet,amount.
        """
        csv_path = os.path.expanduser(csv_path)
        run_start = self.clock_time()
        in_process_file = self._get_in_process_json_path(csv_path)
        if not in_process_file.exists():
            logger.error(f"missing in-process file: ({in_process_file})")
            return
        self.in_process = json.loads(in_process_file.read_text(encoding="utf-8"))
        total_items = len(self.in_process)
        left_items = sum(not i["finalized"] for i in self.in_process.values())
        logger.info(f"going to confirm {left_items} left not verified, out of {total_items} records")

        asyncit = Asyncit(
            save_output=True, save_as_json=True, pool_size=200, rate_limit=[{"period_sec": 5, "max_calls": 100}]
        )
        for i, item in self.in_process.items():
            if not item.get("signature"):
                continue
            if item.get("finalized"):
                continue
            asyncit.run(self.confirm_transaction, item["signature"], response_extra={"index": str(i)})
        asyncit.wait()
        confirm_result = asyncit.get_output()
        if not confirm_result:
            logger.info("nothing to update in process file")
            return
        for result in confirm_result:
            self.in_process[result["index"]]["finalized"] = result["confirmed"]
        in_process_file.write_text(json.dumps(self.in_process), encoding="utf-8")
        total_finalized = sum(i["finalized"] for i in self.in_process.values())
        logger.info(
            f"Done after {self._elapsed_time(run_start)}. total finalized: {total_finalized} / {len(self.in_process)}"
        )

    def confirm_transaction(
        self,
        tx_sig: str,
        commitment: Commitment = Finalized,
        sleep_seconds: float = 1.0,
        response_extra: Optional[Dict] = None,
        timeout: Optional[int] = 30,
    ) -> Dict:
        """Confirm the transaction identified by the specified signature.

        :param tx_sig: The transaction signature to confirm.
        :param commitment: Bank state to query. It can be either "finalized", "confirmed" or "processed".
        :param sleep_seconds: The number of seconds to sleep when polling the signature status.
        :param response_extra: Extra data for response, in dict format (will be added as key: value in response)
        :param timeout: Timeout in seconds to wait for confirmation
        """
        timeout = time.time() + timeout
        resp = {}
        last_confirmation_amount = 0
        max_retries = 60
        confirmed = False
        response = DotDict(signature=tx_sig, confirmed=confirmed)
        if response_extra:
            response.update(response_extra)
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
                    logger.debug(f"transaction {tx_sig} confirmed (rank: {confirmation_rank})")
                    confirmed = True
                    break
                confirmation_amount = resp_value["confirmations"]
                if last_confirmation_amount != confirmation_amount:
                    logger.info(f"transaction {tx_sig} confirmed by {confirmation_amount} validators")
                    last_confirmation_amount = confirmation_amount
            time.sleep(sleep_seconds)
        else:
            maybe_rpc_error = resp.get("error")
            logger.error(f"Unable to confirm transaction {tx_sig}. {maybe_rpc_error}")
        return response.update(confirmed=confirmed)

    def bulk_status(self, csv_path: str):
        """Get transfer status for a given transfer csv file.

        :param csv_path: Path to a csv file to retrieve transfer data for.
        """
        csv_path = os.path.expanduser(csv_path)
        in_process_file = self._get_in_process_json_path(csv_path)
        response = DotDict(cav_path=csv_path, json_path=str(in_process_file))
        if not in_process_file.exists():
            logger.error(f"missing in-process file: ({in_process_file})")
            return response.update(err="missing json file")
        self.in_process = json.loads(in_process_file.read_text(encoding="utf-8"))
        return self.sum_info(self.in_process)
