import time
import logging
from enum import IntEnum

from construct import Bytes, Int8ul
from construct import Struct as cStruct  # type: ignore
from solana.keypair import Keypair
from solana.rpc.api import Client
from solana.publickey import PublicKey
from solana.rpc.types import TxOpts
from solana.transaction import AccountMeta, Transaction, TransactionInstruction

from .metadata import Metadata
from .constants import METADATA_PROGRAM_ID

logger = logging.getLogger(__name__)


class InstructionType(IntEnum):
    CREATE_METADATA = 0
    UPDATE_METADATA = 1


class Transactions:
    def __init__(self):
        self.metadata = Metadata()

    def create_data_for_update_metadata_instruction(self, name, symbol, uri, fee, creators, verified, share):
        _data = (
            bytes([1])
            + self.metadata.get_data_buffer(name, symbol, uri, fee, creators, verified, share)
            + bytes([0, 0])
        )
        instruction_layout = cStruct(
            "instruction_type" / Int8ul,
            "args" / Bytes(len(_data)),
        )
        return instruction_layout.build(
            dict(
                instruction_type=InstructionType.UPDATE_METADATA,
                args=_data,
            )
        )

    def create_update_metadata_instruction(self, data, update_authority, mint_key):
        metadata_account = self.metadata.get_metadata_account(mint_key)
        keys = [
            AccountMeta(pubkey=metadata_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=update_authority, is_signer=True, is_writable=False),
        ]
        return TransactionInstruction(keys=keys, program_id=METADATA_PROGRAM_ID, data=data)

    def create_update_token_metadata_tx(
        self,
        source_account,
        mint_address,
        link,
        name,
        symbol,
        fee,
        creators_addresses,
        creators_verified,
        creators_share,
    ):
        """Updates the json metadata for a given mint token id."""
        mint_account = PublicKey(mint_address)
        signers = [source_account]

        tx = Transaction()
        update_metadata_data = self.create_data_for_update_metadata_instruction(
            name,
            symbol,
            link,
            fee,
            creators_addresses,
            creators_verified,
            creators_share,
        )
        update_metadata_ix = self.create_update_metadata_instruction(
            update_metadata_data,
            source_account.public_key,
            mint_account,
        )
        tx = tx.add(update_metadata_ix)
        return tx, signers

    def execute(
        self,
        api_endpoint,
        tx,
        signers,
        max_retries=3,
        skip_confirmation=True,
        max_timeout=60,
        target=20,
        finalized=True,
    ):
        client = Client(api_endpoint)
        signers = list(map(Keypair, set(map(lambda s: s.seed, signers))))
        for attempt in range(max_retries):
            try:
                result = client.send_transaction(tx, *signers, opts=TxOpts(skip_preflight=True))
                signatures = [x.signature for x in tx.signatures]
                if not skip_confirmation:
                    self.await_confirmation(client, signatures, max_timeout, target, finalized)
                return result
            except Exception as ex:
                logger.error(f"Failed attempt {attempt}: {ex}")
                continue
        return None

    def await_confirmation(self, client, signatures, max_timeout=60, target=20, finalized=True):
        elapsed = 0
        while elapsed < max_timeout:
            sleep_time = 1
            time.sleep(sleep_time)
            elapsed += sleep_time
            resp = client.get_signature_statuses(signatures)
            if resp["result"]["value"][0] is not None:
                confirmations = resp["result"]["value"][0]["confirmations"]
                is_finalized = resp["result"]["value"][0]["confirmationStatus"] == "finalized"
            else:
                continue
            if not finalized:
                if confirmations >= target or is_finalized:
                    logger.info(f"Took {elapsed} seconds to confirm transaction")
                    return
            elif is_finalized:
                logger.info(f"Took {elapsed} seconds to confirm transaction")
                return
