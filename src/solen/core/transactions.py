import json
import time
import base64
import struct
import logging
from typing import Union

from construct import Bytes, Int8ul
from construct import Struct as cStruct  # type: ignore
from asyncit.dicts import DotDict
from solana.sysvar import SYSVAR_RENT_PUBKEY
from solana.keypair import Keypair
from solana.rpc.api import Client
from solana.rpc.core import RPCException
from solana.publickey import PublicKey
from solana.rpc.types import TxOpts
from solana.exceptions import SolanaRpcException
from solana.transaction import AccountMeta, Transaction, TransactionInstruction
from spl.token._layouts import MINT_LAYOUT, ACCOUNT_LAYOUT
from spl.token.constants import TOKEN_PROGRAM_ID
from solana.system_program import SYS_PROGRAM_ID as SYSTEM_PROGRAM_ID
from solana.system_program import TransferParams, CreateAccountParams, transfer, create_account
from spl.token.instructions import BurnParams, MintToParams
from spl.token.instructions import TransferParams as SPLTransferParams
from spl.token.instructions import InitializeMintParams
from spl.token.instructions import burn as spl_burn
from spl.token.instructions import mint_to
from spl.token.instructions import transfer as spl_transfer
from spl.token.instructions import initialize_mint, get_associated_token_address

from .metadata import Metadata, InstructionType
from .constants import METADATA_PROGRAM_ID

logger = logging.getLogger(__name__)


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

    def create_master_edition_instruction(
        self,
        mint: PublicKey,
        update_authority: PublicKey,
        mint_authority: PublicKey,
        payer: PublicKey,
        supply: Union[int, None],
    ):
        logger.info(f"creating master edition instruction for: {mint}")
        edition_account = self.metadata.mint_authority(mint)
        metadata_account = self.metadata.get_metadata_account(mint)
        if supply is None:
            data = struct.pack("<BB", 10, 0)
        else:
            data = struct.pack("<BBQ", 10, 1, supply)
        keys = [
            AccountMeta(pubkey=edition_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=mint, is_signer=False, is_writable=True),
            AccountMeta(pubkey=update_authority, is_signer=True, is_writable=False),
            AccountMeta(pubkey=mint_authority, is_signer=True, is_writable=False),
            AccountMeta(pubkey=payer, is_signer=True, is_writable=False),
            AccountMeta(pubkey=metadata_account, is_signer=False, is_writable=False),
            AccountMeta(pubkey=PublicKey(TOKEN_PROGRAM_ID), is_signer=False, is_writable=False),
            AccountMeta(pubkey=PublicKey(SYSTEM_PROGRAM_ID), is_signer=False, is_writable=False),
            AccountMeta(pubkey=PublicKey(SYSVAR_RENT_PUBKEY), is_signer=False, is_writable=False),
        ]
        return TransactionInstruction(
            keys=keys,
            program_id=METADATA_PROGRAM_ID,
            data=data,
        )

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
    ) -> DotDict:
        client = Client(api_endpoint)
        signers = list(map(Keypair, set(map(lambda s: s.seed, signers))))
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"attempt {attempt} to execute transaction")
                result = client.send_transaction(tx, *signers, opts=TxOpts(skip_preflight=True))
                logger.info(f"execute transaction signature result: {result}")
                signatures = [x.signature for x in tx.signatures]
                if skip_confirmation:
                    return DotDict(result)
                if self.await_confirmation(client, signatures, max_timeout, target, finalized):
                    return DotDict(result).update(ok=True)
            except RPCException as ex:
                message = dict(ex.args[0])["message"]
                logger.error(f"Failed attempt {attempt}, RPC error: {message}")
                time.sleep(1)
            except SolanaRpcException as ex:
                message = dict(ex.args[0])["message"]
                logger.error(f"Failed attempt {attempt}, RPC ex: {message}")
                time.sleep(1)
            except Exception as ex:
                logger.exception(f"Failed attempt {attempt}: {ex}")
                time.sleep(1)
        return DotDict(ok=False)

    def await_confirmation(self, client, signatures, max_timeout=60, target=20, finalized=True) -> bool:
        logger.info(f"going to wait {max_timeout} sec for confirmations")
        signatures = signatures if isinstance(signatures, list) else [signatures]
        run_start = time.perf_counter()
        sleep_time = 1
        while time.perf_counter() - run_start < max_timeout:
            elapsed = int(time.perf_counter() - run_start)
            resp = client.get_signature_statuses(signatures, search_transaction_history=True)
            error = resp.get("error")
            if error:
                logger.error(f"failed to get signature status: {error}")
            elif resp["result"]["value"][0] is not None:
                confirmations = resp["result"]["value"][0]["confirmations"]
                is_finalized = resp["result"]["value"][0]["confirmationStatus"] == "finalized"
                logger.info(f"transaction {signatures} confirmed by {confirmations} validators")
                if not finalized:
                    if confirmations >= target or is_finalized:
                        logger.info(f"Took {elapsed} seconds to confirm transaction")
                        return True
                elif is_finalized:
                    logger.info(f"Took {elapsed} seconds to confirm transaction")
                    return True
            time.sleep(sleep_time)
        logger.error("timeout occurred on waiting for transaction")
        return False

    def wallet(self):
        """Generate a new random public/private keypair of a wallet and return the address and private key.
        No network calls are made here
        """
        account = Keypair()
        pub_key = account.public_key
        private_key = list(account.seed)
        return json.dumps({"address": str(pub_key), "private_key": private_key})

    def topup(self, api_endpoint: str, sender_account: str, to: str, amount: int = None):
        """topup sends a small amount of SOL to the destination account (to handle gas fees)
        by invoking Transfer from the System Program.
        Return a status flag of success or fail and the native transaction data.

        :param api_endpoint: The RPC endpoint to connect the network. (devnet, mainnet).
        :param sender_account: The base58 encoded public key of the destination address.
        :param to: The base58 encoded public key of the destination address
        :param amount: (Union[int, None]) This is the number of lamports to send to the destination address.
            If None (default), then the minimum rent exemption balance is transferred.
        """
        # Connect to the api_endpoint
        client = Client(api_endpoint)
        # List accounts
        dest_account = PublicKey(to)
        # List signers
        signers = [sender_account]
        # Start transaction
        tx = Transaction()
        # Determine the amount to send
        if amount is None:
            min_rent_reseponse = client.get_minimum_balance_for_rent_exemption(ACCOUNT_LAYOUT.sizeof())
            lamports = min_rent_reseponse["result"]
        else:
            lamports = int(amount)
        # Generate transaction
        transfer_ix = transfer(
            TransferParams(from_pubkey=sender_account.public_key, to_pubkey=dest_account, lamports=lamports)
        )
        tx = tx.add(transfer_ix)
        return tx, signers

    def create_mint_account_transactions(self, api_endpoint, source_account, name, symbol, fees):
        """Deploy - create a new NFT token by
        - Creating a new account from a randomly generated address (invokes CreateAccount from the System Program)
        - Invoking InitializeMint on the new account
        - Initializing the metadata for this account by invoking the
            CreateMetatdata instruction from the Metaplex protocol

        :param api_endpoint: (str) The RPC endpoint to connect the network. (devnet, mainnet)
        """
        # Initalize Client
        client = Client(api_endpoint)
        # List non-derived accounts
        mint_account = Keypair()
        token_account = TOKEN_PROGRAM_ID
        # List signers
        signers = [source_account, mint_account]
        # Start transaction
        tx = Transaction()
        # Get the minimum rent balance for a mint account
        lamports = client.get_minimum_balance_for_rent_exemption(MINT_LAYOUT.sizeof()).get("result")
        space = MINT_LAYOUT.sizeof()
        # Generate Mint
        create_mint_account_ix = create_account(
            CreateAccountParams(
                from_pubkey=source_account.public_key,
                new_account_pubkey=mint_account.public_key,
                lamports=lamports,
                space=space,
                program_id=token_account,
            )
        )
        tx = tx.add(create_mint_account_ix)
        initialize_mint_ix = initialize_mint(
            InitializeMintParams(
                decimals=0,
                program_id=token_account,
                mint=mint_account.public_key,
                mint_authority=source_account.public_key,
                freeze_authority=source_account.public_key,
            )
        )
        tx = tx.add(initialize_mint_ix)
        # Create Token Metadata
        create_metadata_ix = self.metadata.create_metadata_instruction(
            data=self.metadata.create_metadata_instruction_data(name, symbol, fees, [str(source_account.public_key)]),
            update_authority=source_account.public_key,
            mint_key=mint_account.public_key,
            mint_authority_key=source_account.public_key,
            payer=source_account.public_key,
        )
        tx = tx.add(create_metadata_ix)
        return tx, signers, str(mint_account.public_key)

    def create_mint_transaction(self, api_endpoint, source_account, contract_key, dest_key, link, supply=1):
        """Mint a token into the wallet specified by address.
        Additional character fields: name, description, link, created
        These are text fields intended to be written directly to the blockchain.
        content is an optional JSON string for customer-specific data.
        Return a status flag of success or fail and the native transaction data.
        """
        # Initialize Client
        client = Client(api_endpoint)
        # List non-derived accounts
        mint_account = PublicKey(contract_key)
        user_account = PublicKey(dest_key)
        token_account = TOKEN_PROGRAM_ID
        # List signers
        signers = [source_account]
        # Start transaction
        tx = Transaction()
        # Create Associated Token Account
        associated_token_account = get_associated_token_address(user_account, mint_account)
        associated_token_account_info = client.get_account_info(associated_token_account)
        # Check if PDA is initialized. If not, create the account
        account_info = associated_token_account_info["result"]["value"]
        if account_info is not None:
            account_state = ACCOUNT_LAYOUT.parse(base64.b64decode(account_info["data"][0])).state
        else:
            account_state = 0
        if account_state == 0:
            associated_token_account_ix = self.metadata.create_associated_token_account_instruction(
                associated_token_account=associated_token_account,
                payer=source_account.public_key,  # signer
                wallet_address=user_account,
                token_mint_address=mint_account,
            )
            tx = tx.add(associated_token_account_ix)
            # Mint NFT to the newly create associated token account
        mint_to_ix = mint_to(
            MintToParams(
                program_id=TOKEN_PROGRAM_ID,
                mint=mint_account,
                dest=associated_token_account,
                mint_authority=source_account.public_key,
                amount=1,
                signers=[source_account.public_key],
            )
        )
        tx = tx.add(mint_to_ix)
        metadata = self.metadata.get_metadata(client, mint_account)
        update_metadata_data = self.metadata.update_metadata_instruction_data(
            metadata["data"]["name"],
            metadata["data"]["symbol"],
            link,
            metadata["data"]["seller_fee_basis_points"],
            metadata["data"]["creators"],
            metadata["data"]["verified"],
            metadata["data"]["share"],
        )
        update_metadata_ix = self.create_update_metadata_instruction(
            update_metadata_data,
            source_account.public_key,
            mint_account,
        )
        tx = tx.add(update_metadata_ix)
        create_master_edition_ix = self.create_master_edition_instruction(
            mint=mint_account,
            update_authority=source_account.public_key,
            mint_authority=source_account.public_key,
            payer=source_account.public_key,
            supply=supply,
        )
        tx = tx.add(create_master_edition_ix)
        return tx, signers

    def send(
        self, api_endpoint: str, source_account: str, contract_key: str, sender_key: str, dest_key: str, private_key
    ):
        """
        Send a token from one user account to another user account.
        Fetching the AssociatedTokenAccount from a Program Derived Address for the sender
        Fetching or creatign the AssociatedTokenAccount from a Program Derived Address for the receiver
        Invoking Transfer (from the Token Program) with the receiver's AssociatedTokenAccount as the destination

        :param api_endpoint: The RPC endpoint to connect the network.
        :param source_account: The signer / payer.
        :param contract_key: The base58 encoded public key of the mint address.
        :param sender_key: The base58 encoded public key of the source address.
        :param dest_key: The base58 encoded public key of the destination address.
        :param private_key: The encrypted private key of the sender.
        """
        # Initialize Client
        client = Client(api_endpoint)
        # List non-derived accounts
        owner_account = Keypair(private_key)  # Owner of contract
        sender_account = PublicKey(sender_key)  # Public key of `owner_account`
        token_account = TOKEN_PROGRAM_ID
        mint_account = PublicKey(contract_key)
        dest_account = PublicKey(dest_key)
        # This is a very rare care, but in the off chance that the source wallet is the recipient of a transfer
        # we don't need a list of 2 keys
        signers = [source_account, owner_account]
        # Start transaction
        tx = Transaction()
        # Find PDA for sender
        token_pda_address = get_associated_token_address(sender_account, mint_account)
        if client.get_account_info(token_pda_address)["result"]["value"] is None:
            raise Exception
        # Check if PDA is initialized for receiver. If not, create the account
        associated_token_account = get_associated_token_address(dest_account, mint_account)
        associated_token_account_info = client.get_account_info(associated_token_account)
        account_info = associated_token_account_info["result"]["value"]
        if account_info is not None:
            account_state = ACCOUNT_LAYOUT.parse(base64.b64decode(account_info["data"][0])).state
        else:
            account_state = 0
        if account_state == 0:
            associated_token_account_ix = self.metadata.create_associated_token_account_instruction(
                associated_token_account=associated_token_account,
                payer=source_account.public_key,  # signer
                wallet_address=dest_account,
                token_mint_address=mint_account,
            )
            tx = tx.add(associated_token_account_ix)
            # Transfer the Token from the sender account to the associated token account
        spl_transfer_ix = spl_transfer(
            SPLTransferParams(
                program_id=token_account,
                source=token_pda_address,
                dest=associated_token_account,
                owner=sender_account,
                signers=[],
                amount=1,
            )
        )
        tx = tx.add(spl_transfer_ix)
        return tx, signers

    def burn(self, api_endpoint: str, contract_key: str, owner_key: str, private_key):
        """Burn a token, permanently removing it from the blockchain.
        Return a status flag of success or fail and the native transaction data.

        :param api_endpoint: The RPC endpoint to connect the network.
        :param contract_key: The base58 encoded public key of the mint address
        :param owner_key: The base58 encoded public key of the owner address
        :param private_key: The encrypted private key of the owner
        """
        # Initialize Client
        client = Client(api_endpoint)
        # List accounts
        owner_account = PublicKey(owner_key)
        token_account = TOKEN_PROGRAM_ID
        mint_account = PublicKey(contract_key)
        # List signers
        signers = [Keypair(private_key)]
        # Start transaction
        tx = Transaction()
        # Find PDA for sender
        token_pda_address = get_associated_token_address(owner_account, mint_account)
        if client.get_account_info(token_pda_address)["result"]["value"] is None:
            raise Exception
        # Burn token
        burn_ix = spl_burn(
            BurnParams(
                program_id=token_account,
                account=token_pda_address,
                mint=mint_account,
                owner=owner_account,
                amount=1,
                signers=[],
            )
        )
        tx = tx.add(burn_ix)
        return tx, signers
