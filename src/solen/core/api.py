import json
import logging

from construct import Struct as cStruct  # type: ignore
from asyncit.dicts import DotDict

from ..context import Context
from .transactions import Transactions

logger = logging.getLogger(__name__)


class API:
    def __init__(self, context: Context):
        self.context = context
        self.transactions = Transactions()

    @property
    def keypair(self):
        return self.context.keypair

    @property
    def api_endpoint(self):
        return self.context.rpc_endpoint

    def create_new_token_contract(
        self,
        name,
        symbol,
        seller_fee_basis_points,
        max_retries=3,
        skip_confirmation=False,
        max_timeout=60,
        target=20,
        finalized=True,
    ) -> DotDict:
        """Create a new token contract on the blockchain.
        Takes the network ID and contract name, plus initialisers of name and symbol.
        Returns status code of success or fail, the contract address, and the native transaction data.
        """
        try:
            mint_account_data = dict(
                api_endpoint=self.api_endpoint,
                source_account=self.keypair,
                name=name,
                symbol=symbol,
                fees=seller_fee_basis_points,
            )
            tx, signers, contract = self.transactions.create_mint_account_transactions(**mint_account_data)
            logger.info(f"mint account public key: {contract}")
            response = self.transactions.execute(
                self.api_endpoint,
                tx,
                signers,
                max_retries=max_retries,
                skip_confirmation=skip_confirmation,
                max_timeout=max_timeout,
                target=target,
                finalized=finalized,
            )
            if not response or not response.ok:
                logger.error("failed to deploy token contract")
                return response
            response.contract = contract
            response.status = 200
            return response.update(ok=True)
        except Exception as ex:
            return DotDict(ok=False, err=str(ex), status=400)

    def topup(
        self,
        api_endpoint,
        to,
        amount=None,
        max_retries=3,
        skip_confirmation=False,
        max_timeout=60,
        target=20,
        finalized=True,
    ):
        """Send a small amount of native currency to the specified wallet to handle gas fees.
        Return a status flag of success or fail and the native transaction data.
        """
        try:
            tx, signers = self.transactions.topup(api_endpoint, self.keypair, to, amount=amount)
            resp = self.transactions.execute(
                api_endpoint,
                tx,
                signers,
                max_retries=max_retries,
                skip_confirmation=skip_confirmation,
                max_timeout=max_timeout,
                target=target,
                finalized=finalized,
            )
            resp["status"] = 200
            return json.dumps(resp)
        except Exception as ex:
            return json.dumps({"status": 400, "err": str(ex)})

    def mint_nft(
        self,
        contract_key,
        dest_key,
        link,
        max_retries=3,
        skip_confirmation=False,
        max_timeout=60,
        target=20,
        finalized=True,
        supply=1,
    ) -> DotDict:
        """Mints an NFT to an account, updates the metadata and creates a master edition."""
        logger.info(f"going to mint {dest_key}")
        tx, signers = self.transactions.create_mint_transaction(
            self.api_endpoint, self.keypair, contract_key, dest_key, link, supply=supply
        )
        execute_response = self.transactions.execute(
            self.api_endpoint,
            tx,
            signers,
            max_retries=max_retries,
            skip_confirmation=skip_confirmation,
            max_timeout=max_timeout,
            target=target,
            finalized=finalized,
        )
        if not execute_response:
            return DotDict(ok=False)
        response = DotDict(execute_response)
        response.status = 200
        return response

    def burn_nft(self, mint_address, max_retries=3, skip_confirmation=False, max_timeout=60, target=20, finalized=True):
        """Burn a token, permanently removing it from the blockchain.
        Return a status flag of success or fail and the native transaction data.
        """
        tx, signers = self.transactions.create_burn_transaction(
            api_endpoint=self.api_endpoint,
            contract_key=mint_address,
            owner_key=self.keypair.public_key,
            private_key=self.keypair,
        )
        execute_response = self.transactions.execute(
            self.api_endpoint,
            tx,
            signers,
            max_retries=max_retries,
            skip_confirmation=skip_confirmation,
            max_timeout=max_timeout,
            target=target,
            finalized=finalized,
        )
        if not execute_response:
            return DotDict(ok=False)
        response = DotDict(execute_response)
        response.status = 200
        return response
