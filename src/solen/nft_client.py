import os
import json
import time
import base64
import struct
import logging
from typing import Dict, List, Union, Optional
from datetime import datetime, timedelta

import base58
from asyncit import Asyncit
from asyncit.dicts import DotDict
from solana.publickey import PublicKey
from solana.rpc.types import TokenAccountOpts
from spl.token._layouts import MINT_LAYOUT, ACCOUNT_LAYOUT
from spl.token.constants import TOKEN_PROGRAM_ID
from solana.rpc.commitment import COMMITMENT_RANKS, Confirmed, Finalized, Commitment

from .context import Context
from .response import Ok, Err, Response
from .core.errors import token_metadata_errors
from .core.metadata import Metadata
from .core.transactions import Transactions
from .utils.bulk_handler import BulkHandler

logger = logging.getLogger(__name__)


class NFTClient:  # pylint: disable=too-many-instance-attributes
    """NFT Client class.

    :param env: The Solana env (options are based on the config file)

    The Solana RPC endpoint is taken from the config file - based on the given env parameter.
    For example, using the :ref:`config file <index:config file>` in the example and "dev" parameter,
    the RPC endpoint will be:`https://api.devnet.solana.com`
    """

    def __init__(self, env: str, context: Context = None):
        """Init NFT Client."""
        self.env = env
        self.context = context or Context(env)
        self.client = self.context.client
        self.keypair = self.context.keypair
        self.config_folder = self.context.config_folder
        self.transfers_data_folder = self.config_folder.joinpath("transfers")
        self.updates_data_folder = self.config_folder.joinpath("updates")
        self.bulk_update_nft_handler = BulkHandler(
            self.client,
            self.env,
            self.updates_data_folder,
            self.update_token_metadata,
            self.bulk_sum_info,
            "update",
            ["mint_address"],
        )
        self.rpc_endpoint = self.context.rpc_endpoint
        self.metadata = Metadata()
        self.transaction = Transactions()
        self.clock_time = time.perf_counter
        self.run_start = self.clock_time()
        os.makedirs(self.transfers_data_folder, exist_ok=True)
        os.makedirs(self.updates_data_folder, exist_ok=True)

    def _set_start_time(self):
        self.run_start = self.clock_time()

    def _elapsed_time(self, run_start=None):
        run_start = run_start or self.run_start
        elapsed_time = self.clock_time() - run_start
        return str(timedelta(seconds=elapsed_time)).split(".", maxsplit=1)[0]

    def get_data(self, mint_key: str, sort_creators_by_share: bool = True) -> Dict:
        """Get the NFT On-Chain data. The creators data returned sorted by share.

         :param mint_key: The NFT mint address.
         :param sort_creators_by_share: If true the creators, verified and share lists will be sorted correspondingly
             by the share amount - the highest first (default: true).

        >>> from solen import NFTClient
        >>> nft_client = NFTClient("main")
        >>> metadata = nft_client.get_data("DAysz5tmEMQBhXgcQHXrhQaF3rGwVw3LKoj5vMHY9vxM")
        >>> print(json.dumps(metadata, indent=4))  # doctest: +SKIP
        {"update_authority": "AuoD4FKLSDKpuNm7y1G5RX3jBdrXerHfaVjfP415miET",
         "mint": "DAysz5tmEMQBhXgcQHXrhQaF3rGwVw3LKoj5vMHY9vxM",
         "data": {
             "name": "Monkey #3882",
             "symbol": "ML",
             "uri": "https://arweave.net/q54T5RnKno8h8W_PtVL9xUQXh6tPZw4eTAxphS1Og38",
             "seller_fee_basis_points": 450,
             "creators": [
                 "BAjb6D4n8LGrzGpncShKFxkD8dpGKM3KoZ6yrmSrai8k",
                 "AuoD4FKLSDKpuNm7y1G5RX3jBdrXerHfaVjfP415miET",
                 "3xiSExYoVT63E8bMQpF4FAYfXSGU9CMm5E5zBz1cDKGb"
             ],
             "verified": [0, 0, 1],
             "share": [100, 0, 0]
         },
         "primary_sale_happened": true,
         "is_mutable": true}
        >>> print(metadata.data.name) # doctest: +SKIP
        Monkey #3882
        """
        metadata_account = self.metadata.get_metadata_account(mint_key)
        metadata = base64.b64decode(self.client.get_account_info(metadata_account)["result"]["value"]["data"][0])
        metadata = DotDict(self.metadata.unpack_metadata_account(metadata))
        if sort_creators_by_share:
            zipped = zip(
                *sorted(zip(metadata.data.share, metadata.data.verified, metadata.data.creators), reverse=True)
            )
            metadata.data.creators, metadata.data.share, metadata.data.verified = [list(i) for i in zipped]
        return metadata

    def bulk_get_data(self, mint_key_list: List[str], sort_creators_by_share: bool = True) -> List[Dict]:
        """Bulk call to get_data function, to get the NFT On-Chain data of nfts in the input list.

        :param mint_key_list: mint address list to query
        :param sort_creators_by_share: If true the creators, verified and share lists will be sorted correspondingly
            by the share amount - the highest first (default: true).

        >>> from solen import NFTClient
        >>> nft_client = NFTClient("main")
        >>> metadata = nft_client.nft.bulk_get_data(["DAysz5tmEMQBhXgcQHXrhQaF3rGwVw3LKoj5vMHY9vxM",
        >>>                                          "7Sde2VNGTcHv5wmgrYTvGW9h8Umiob5MdTq6Y7BuTw7h"])
        """
        asyncit = Asyncit(
            save_output=True, save_as_json=True, pool_size=200, rate_limit=[{"period_sec": 5, "max_calls": 200}]
        )
        for mint_key in mint_key_list:
            asyncit.run(self.get_data, mint_key, sort_creators_by_share)
        asyncit.wait()
        return asyncit.get_output()

    def get_historical_holders_associate_accounts(self, mint_address: str):
        """get all historical holders accounts for a given NFT.
        The function returna the associated accounts and not the owners accounts.
        To get the owners need to use get_historical_holders_owners.

        :param mint_address: mint address to query.
        """
        largest_accounts = self.client.get_token_largest_accounts(PublicKey(mint_address))
        return [i["address"] for i in largest_accounts["result"]["value"]]

    def get_owner_of_associate_account(self, associated_address: str):
        """get the owner of a given associated account.

        :param associated_address: associated address to query.
        """
        largest_account_info = self.client.get_account_info(PublicKey(associated_address))
        data = ACCOUNT_LAYOUT.parse(base64.b64decode(largest_account_info["result"]["value"]["data"][0]))
        return base58.b58encode(bytes(struct.unpack("<" + "B" * 32, data.owner)))

    def get_holders(self, mint_address: str):
        """get all historical holders owners for a given NFT.

        :param mint_address: mint address to query.

        >>> from solen import NFTClient
        >>> nft_client = NFTClient("main")
        >>> nft_client.get_holders("7Sde2VNGTcHv5wmgrYTvGW9h8Umiob5MdTq6Y7BuTw7h")
            ['FPqcXeEAt3WtRD8QcSVRcX9WD1zuM5xxvJQhfE9XJbLF',
            'AuoD4FKLSDKpuNm7y1G5RX3jBdrXerHfaVjfP415miET']
        """
        largest_accounts = self.get_historical_holders_associate_accounts(mint_address)
        return [self.get_owner_of_associate_account(a).decode("utf-8") for a in largest_accounts]

    def get_current_holder(self, mint_address: str) -> str:
        """get current holder owners for a given NFT.

        :param mint_address: mint address to query.

        >>> from solen import NFTClient
        >>> nft_client = NFTClient("main")
        >>> nft_client.get_current_holder("7Sde2VNGTcHv5wmgrYTvGW9h8Umiob5MdTq6Y7BuTw7h")
            'FPqcXeEAt3WtRD8QcSVRcX9WD1zuM5xxvJQhfE9XJbLF'
        """
        largest_accounts = self.get_historical_holders_associate_accounts(mint_address)
        return self.get_owner_of_associate_account(largest_accounts[0]).decode("utf-8")

    def get_transactions(self, mint_address: str) -> List[Dict]:
        """get historical transactions for a given NFT.

        :param mint_address: mint address to query.

        >>> from solen import NFTClient
        >>> nft_client = NFTClient("main")
        >>> transactions = nft_client.get_transactions("9DAhGeEUYboU4EvGNvgPajZ6Acd9UfDX9aB5zGv6oTJj")
        [{'blockTime': 1641486108,
          'confirmationStatus': 'finalized',
          'err': None,
          'memo': None,
          'signature': '3H2SvadvjjwwWoCjmhC68sqVVJK79oXkzokfPMscNvX5RYatzVPceLSzTEztujSXZPf5FSySaYVe4oigkyNG88e2',
          'slot': 115072701,
          'time': datetime.datetime(2022, 1, 6, 18, 21, 48)},...]
        >>> transactions[0].signature
            '3H2SvadvjjwwWoCjmhC68sqVVJK79oXkzokfPMscNvX5RYatzVPceLSzTEztujSXZPf5FSySaYVe4oigkyNG88e2'
        """

        def add_time_to_data(data: Dict) -> Dict:
            timestamp = data.get("blockTime")
            if not timestamp:
                return data
            data["datetime"] = datetime.fromtimestamp(timestamp)
            return data

        response = self.client.get_confirmed_signature_for_address2(PublicKey(mint_address))
        err = response.get("error")
        if err:
            logger.error(f"failed to get transactions, err code: {err['code']}, message: {err['message']})")
            return []
        signatures_data = response["result"]
        return [DotDict(add_time_to_data(d)) for d in signatures_data]

    def get_transaction_data(self, signatures: str) -> Dict:
        """get transaction data.

        :param signatures: transaction signatures.
        """
        transaction = self.client.get_transaction(signatures)
        if not transaction["result"]:
            logger.error(f"failed to get transaction data for {signatures}")
            return {}
        return DotDict(transaction["result"]["meta"])

    def _parse_token_value(self, value: Dict) -> Dict:
        """Parse extract meaningful dict data from the extended token account data."""
        associate_account_pubkey = value["pubkey"]
        sol_balance = value["account"]["lamports"] / pow(10, 9)
        info = value["account"]["data"]["parsed"]["info"]
        token_address = info["mint"]
        update_authority = info["owner"]
        amount = float(info["tokenAmount"]["uiAmountString"])
        hold_by_owner = amount > 0
        return DotDict(
            dict(
                account=associate_account_pubkey,
                sol_balance=sol_balance,
                token=token_address,
                token_balance=amount,
                hold_by_owner=hold_by_owner,
                update_authority=update_authority,
            )
        )

    def get_all_nft_accounts_by_owner(self, owner: Optional[Union[PublicKey, str]] = None) -> List:
        """Get all NFT accounts owned by the given owner.

        :param owner: The owner address to query for NFTs.
        """
        owner = owner or self.keypair.public_key
        commitment: Commitment = Finalized
        encoding: str = "jsonParsed"
        opt = TokenAccountOpts(program_id=TOKEN_PROGRAM_ID, encoding=encoding)
        response = self.client.get_token_accounts_by_owner(PublicKey(str(owner)), opt, commitment)
        return [self._parse_token_value(v) for v in response["result"]["value"]]

    def update_token_metadata(  # pylint: disable=too-many-return-statements
        self,
        mint_address,
        max_retries=1,
        skip_confirmation=False,
        max_timeout=60,
        target=20,
        finalized=True,
        dry_run=False,
        **kwargs,
    ) -> Dict:
        """Updates the metadata for a given NFT.

        :param mint_address: The NFT mint address.
        :param max_retries: Mac retry attempts of send_transaction in case of failure.
        :param skip_confirmation: If true send transfer will not be coffirmed. It might be faster.
        :param max_timeout: Max timeout for transaction confirmation. Not used if skip_confirmation is True.
        :param target: Target for confirmations transaction confirmation. Not used if skip_confirmation is True.
        :param finalized: If true transaction confirmed only if it has status Finalized, else target is used
            to confirm transaction.
        :param dry_run: If true the transfer will not be executed.
        :param kwargs: The data that need to be changed. Options are: uri, name, symbol, fee, creators

        * uri : str
        * name : str
        * symbol : str
        * fee : int (precentage as int. instead of 4.5% it should be 450)
        * creators : list of dicts. each dict must contain:

            * address : str - the creator address
            * verified : int - 0 or 1
            * share : int - between 0 and 100 (for royalty share between creators)

        >>> from solen import NFTClient
        >>> nft_client = NFTClient("dev")
        >>> response = nft_client.update_token_metadata("CF4wMo1YnK44BL8R8ZpEUpY4iskWX5KAHbRXMUvpqnJL",
        >>>                                             name="Monkey 6001")

        In case os an error, the signature will be in response.err,
        In case os succefull update, the signature will be in response.ok.
        """
        run_start = self.clock_time()
        kwargs = {k: v for k, v in kwargs.items() if v}  # remove keys with None value
        response = DotDict(mint_address=mint_address, confirmed=False, signature="", **kwargs)
        new_creators = kwargs.get("creators")
        if new_creators:
            creators_addresses = [c["address"] for c in new_creators]
            creators_verified = [c["verified"] for c in new_creators]
            creators_share = [c["share"] for c in new_creators]
            if not len(creators_addresses) == len(creators_verified) == len(creators_share):
                err_msg = f"update token failed, bad creators data: {new_creators}"
                logger.error(err_msg)
                return response.update(err=err_msg, ok=False, time=self._elapsed_time(run_start))
        else:
            creators_addresses = creators_verified = creators_share = None

        logger.info(f"going to update token {mint_address} values: {kwargs}")
        current_data = self.get_data(mint_address, sort_creators_by_share=False)
        data = dict(
            source_account=self.keypair,
            mint_address=PublicKey(mint_address),
            link=kwargs.get("uri", current_data.data.uri),
            name=kwargs.get("name", current_data.data.name),
            symbol=kwargs.get("symbol", current_data.data.symbol),
            fee=kwargs.get("fee", current_data.data.seller_fee_basis_points),
            creators_addresses=creators_addresses or list(current_data.data.creators),
            creators_verified=creators_verified or list(current_data.data.verified),
            creators_share=creators_share or list(current_data.data.share),
        )
        if dry_run:
            logger.info(f"dry-run. data: {data}")
            return response.update(signature="test-run", ok=True, time=self._elapsed_time(run_start))
        tx, signers = self.transaction.create_update_token_metadata_tx(**data)
        resp = self.transaction.execute(
            self.rpc_endpoint,
            tx,
            signers,
            max_retries=max_retries,
            skip_confirmation=skip_confirmation,
            max_timeout=max_timeout,
            target=target,
            finalized=finalized,
        )
        if not resp:
            return response.update(err="failed to execute transaction", ok=False, time=self._elapsed_time(run_start))
        transaction_signature = resp["result"]
        if skip_confirmation:
            return response.update(signature=transaction_signature, ok=True, time=self._elapsed_time(run_start))
        logger.info(f"going to verify update transaction signature: {transaction_signature}")
        transaction_data = DotDict(self.get_transaction_data(transaction_signature))
        if not transaction_data:
            return response.update(
                signature=transaction_signature,
                err="failed to get transaction data",
                ok=False,
                time=self._elapsed_time(run_start),
            )
        if transaction_data.status.Err:
            logger.error("\n".join(transaction_data.logMessages))
            err_code = None
            for line in transaction_data.logMessages:
                if "custom program error:" in line:
                    err_code = line.split(":")[-1].strip()
                    err_code = err_code.split("x")[-1]
            err_code_message_decode = token_metadata_errors.get(err_code) if err_code else ""
            msg_message = f"failed to update token data, {err_code_message_decode}"
            logger.error(msg_message)
            return response.update(
                signature=transaction_signature, err=msg_message, ok=False, time=self._elapsed_time(run_start)
            )
        logger.info("update been verified")
        return response.update(
            signature=transaction_signature, ok=True, confirmed=True, time=self._elapsed_time(run_start)
        )

    def bulk_update_init(self, csv_path: str):
        """Create the bulk update config based on given CSV file.

        :param csv_path: Path to a csv file in the format of: wallet,amount.
        """
        with open(csv_path, encoding="UTF-8") as f:
            first_line = f.readlines()[0]
        columns = {i.strip() for i in first_line.split(",")}
        optional_nft_update_key = {"uri", "name", "symbol", "fee", "creators"}
        exiting_nft_update_columns = list(columns.intersection(optional_nft_update_key))
        self.bulk_update_nft_handler.columns = ["mint_address"] + list(exiting_nft_update_columns)
        logger.info(f"updating attributes: {self.bulk_update_nft_handler.columns}")
        in_process_data = self.bulk_update_nft_handler.bulk_init(csv_path)
        logger.info(f"parsed {len(in_process_data)} lines of update commands")
        return len(in_process_data) > 0

    def bulk_sum_info(self, in_process: Dict = None, log_sum: bool = False):
        """Log sum status for

        :param in_process: Current content of the in-process json file (default taken from bulk_update_nft_handler).
        :param log_sum: If true the sum data will be logged (not just returned).
        """
        in_process = in_process or self.bulk_update_nft_handler.in_process

        total_items = len(in_process)
        total_items_with_no_signature = sum(not i["signature"] for i in in_process.values())
        items_with_signature_but_not_finalized = sum(not i["finalized"] for i in in_process.values() if i["signature"])
        total_finalized = sum(i["finalized"] for i in in_process.values())

        if log_sum:
            logger.info(
                f"Total updated: {total_items - total_items_with_no_signature} out of {total_items} items. "
                f"Items with signature but not finalized: {items_with_signature_but_not_finalized}. "
                f"Total finalized: {total_finalized}"
            )

        return dict(
            total_items=total_items,
            items_with_no_signature=total_items_with_no_signature,
            items_with_signature_but_not_finalized=items_with_signature_but_not_finalized,
            total_finalized=total_finalized,
        )

    def bulk_update_nft(self, csv_path: str, dry_run=False, skip_confirm=False):
        """Update multiple NFTs, based on the content of transfer_csv_path.

        :param csv_path: Path to a csv file in the format of: mint_address,VALUE_TO_UPDATE. Options for
            value to update: symbol, name, uri
        :param dry_run: When true the transactions will be skipped.
        :param skip_confirm: When true transaction confirmation will be skipped. Run will be faster but less reliable.

        >>> from solen import NFTClient
        >>> token_client = NFTClient("dev")
        >>> token_client.bulk_update_nft(csv_path)
        when csv should contain update actions data, for example:
        mint_address,symbol
        Cy4y1XGR9pj7vFikWVGrdQAPWCChqV9gQHCLht6eXBLW,MQA
        Cy4y1XGR9pj7vFikWVGrdQAPWCChqV9gQHCLht6eXBLW,MQA
        """
        update_response = self.bulk_update_nft_handler.bulk_run(csv_path, dry_run, skip_confirm)
        if not update_response.ok:
            logger.error(f"failed to update nfts, err: {update_response.err}")
        return self.bulk_update_nft_handler.sum_info()

    def bulk_confirm_transactions(self, csv_path: str):
        """Verify that update transaction signatures are finalized.

        :param csv_path: Path to the csv file that been processed.
        """
        self.bulk_update_nft_handler.bulk_confirm(csv_path)

    def get_update_status(self, csv_path: str):
        """Get update status for a given update csv file.

        :param csv_path: Path to a csv file to retrieve update data for.
        """
        return self.bulk_update_nft_handler.bulk_status(csv_path)
