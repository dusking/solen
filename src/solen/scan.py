import logging
from typing import Dict
from datetime import datetime

from asyncit.dicts import DotDict
from solana.publickey import PublicKey

from .context import Context
from .nft_client import NFTClient

logger = logging.getLogger(__name__)


class Scan:
    def __init__(self, env: str, context: Context = None):
        if env and context:
            logger.error("Need to init with env or context - not both")
        if not env and not context:
            logger.error("Need to init with env or context")
        self.context = context or Context(env)
        self.client = self.context.client

    def get_signatures_for_address(self, address: str, limit=100):
        block_time_ms = 400
        bac_time = block_time_ms * 10
        response = self.client.get_recent_blockhash()
        latest_slot = response["result"]["context"]["slot"]
        block = self.client.get_block(latest_slot - bac_time)
        until_transaction = block["result"]["transactions"][0]["transaction"]["signatures"]
        return self.client.get_confirmed_signature_for_address2(PublicKey(address), limit=limit)

    def get_transaction_data(self, signatures: str) -> DotDict:
        transaction = DotDict(self.client.get_transaction(signatures))
        if transaction.error:
            logger.error(f"failed to get transaction data for {signatures}")
            return DotDict(ok=False, err=transaction.error.message)
        if not transaction["result"]:
            logger.error(f"failed to get transaction data for {signatures}")
            return DotDict(ok=False)
        data = DotDict(transaction["result"]["meta"])
        if len(data.preTokenBalances) > 0:
            logger.info(f"it is NFT {data.preTokenBalances[0]['mint']} transfer transaction: {signatures}")
        return DotDict(ok=True, data=data)

    def get_nft_transfers(self, mint_address):
        nft_client = NFTClient(context=self.context)
        return nft_client.get_transactions(mint_address)

    def get_nft_holders(self, mint_address):
        return self.client.get_token_largest_accounts(PublicKey(mint_address))

    def get_nft_transfer_in_time_range(self):
        response = self.client.get_recent_blockhash()
        latest_slot = response["result"]["context"]["slot"]
        latest_block_timestamp = self.client.get_block_time(latest_slot)
        return latest_block_timestamp

    def get_nft_transfer_in_block(self, block_slot, mint_address):
        data = []
        transactions = self.get_block_transactions(block_slot)
        for transaction in transactions:
            if self.is_it_transfer_transaction_of_nft(transaction, mint_address):
                data.append(transaction)
        return data

    def get_block_transactions(self, block_slot):
        block = self.client.get_block(block_slot)
        return block["result"]["transactions"]

    def is_it_transfer_transaction_of_nft(self, transaction, mint_address):
        pre_token_balances = transaction.get("meta", {}).get("preTokenBalances", [])
        if not pre_token_balances:
            return False
        return pre_token_balances[0].get("mint") == mint_address

    def get_block_time(self, slot):
        """Get the datetime of a given blockhash slot

        :param slot: The blockhash slot to get datetime for.
        """
        block_time = self.client.get_block_time(slot)
        return datetime.fromtimestamp(block_time["result"])

    def get_signature_payload(self, tx_sig: str):
        """
        WIP
        """
        response = self.client.get_confirmed_transaction(tx_sig)
        block_time = response["result"]["blockTime"]
        exec_time = datetime.fromtimestamp(block_time)
