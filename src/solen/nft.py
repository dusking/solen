import json
import base64
import struct
from typing import Dict, List

import base58
from asyncit import Asyncit
from asyncit.dicts import DotDict
from solana.publickey import PublicKey
from solana.rpc.types import TokenAccountOpts
from spl.token._layouts import MINT_LAYOUT, ACCOUNT_LAYOUT
from spl.token.constants import TOKEN_PROGRAM_ID
from solana.rpc.commitment import COMMITMENT_RANKS, Confirmed, Finalized, Commitment

from .core.metadata import Metadata
from .core.transactions import Transactions


class NFT:
    """NFT Client class.

    :param client: Solana Client.
    :param keypair: Keypair of the default source/owner account.
    :param rpc_endpoint: URL of the RPC endpoint.
    """

    def __init__(self, client, keypair, rpc_endpoint):
        """Init NFT Client."""
        self.client = client
        self.keypair = keypair
        self.rpc_endpoint = rpc_endpoint
        self.metadata = Metadata()
        self.transaction = Transactions()

    def get_data(self, mint_key: str, sort_creators_by_share: bool = True) -> Dict:
        """Get the NFT On-Chain data. The creators data returned sorted by share.

         :param mint_key: The NFT mint address.
         :param sort_creators_by_share: If true the creators, verified and share lists will be sorted correspondingly
             by the share amount - the highest first (default: true).

         >>> solen = Solen("main")
         >>> metadata = solen.nft.get_data("DAysz5tmEMQBhXgcQHXrhQaF3rGwVw3LKoj5vMHY9vxM")
         >>> print(json.dumps(metadata, indent=4))

        {
             "update_authority": "AuoD4FKLSDKpuNm7y1G5RX3jBdrXerHfaVjfP415miET",
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
             "is_mutable": true
        }

         >>> print(metadata.data.name)

         Monkey #3882
        """
        metadata_account = self.metadata.get_metadata_account(mint_key)
        metadata = base64.b64decode(self.client.get_account_info(metadata_account)["result"]["value"]["data"][0])
        metadata = DotDict(self.metadata.unpack_metadata_account(metadata))
        if sort_creators_by_share:
            zipped = zip(
                *sorted(zip(metadata.data.creators, metadata.data.share, metadata.data.verified), reverse=True)
            )
            metadata.data.creators, metadata.data.share, metadata.data.verified = zipped
        return metadata

    def bulk_get_data(self, mint_key_list: List[str], sort_creators_by_share: bool = True) -> List[Dict]:
        """Bulk call to get_data function, to get the NFT On-Chain data of nfts in the input list.

        :param mint_key_list: mint address list to query
        :param sort_creators_by_share: If true the creators, verified and share lists will be sorted correspondingly
            by the share amount - the highest first (default: true).

        >>> solen = Solen("main")
        >>> metadata = solen.nft.get_data(["DAysz5tmEMQBhXgcQHXrhQaF3rGwVw3LKoj5vMHY9vxM",
        >>>                                "7Sde2VNGTcHv5wmgrYTvGW9h8Umiob5MdTq6Y7BuTw7h"])
        """
        asyncit = Asyncit(save_output=True, save_as_json=True)
        for mint_key in mint_key_list:
            asyncit.run(self.get_data, mint_key, sort_creators_by_share)
        asyncit.wait()
        return asyncit.get_output()

    def get_historical_holders(self, mint_address: str):
        largest_accounts = self.client.get_token_largest_accounts(PublicKey(mint_address))
        return [i["address"] for i in largest_accounts["result"]["value"]]

    def get_owner_of_associate_account(self, associated_address: str):
        largest_account_info = self.client.get_account_info(PublicKey(associated_address))
        data = ACCOUNT_LAYOUT.parse(base64.b64decode(largest_account_info["result"]["value"]["data"][0]))
        return base58.b58encode(bytes(struct.unpack("<" + "B" * 32, data.owner)))

    def get_historical_holders_owners(self, mint_address: str):
        largest_accounts = self.get_historical_holders(mint_address)
        return [self.get_owner_of_associate_account(a).decode("utf-8") for a in largest_accounts]

    def get_current_holder_owner(self, mint_address: str):
        largest_accounts = self.get_historical_holders(mint_address)
        return self.get_owner_of_associate_account(largest_accounts[0]).decode("utf-8")

    def get_nft_owner(self, mint_address: str):
        response = self.client.get_confirmed_signature_for_address2(PublicKey(mint_address))
        signatures_data = response["result"]
        signatures = [d["signature"] for d in signatures_data]
        transaction = self.client.get_transaction(signatures[0])
        return transaction["result"]["meta"]["postTokenBalances"][0]["owner"]

    def parse_token_value(self, value):
        associate_account_pubkey = value["pubkey"]
        info = value["account"]["data"]["parsed"]["info"]
        token_address = info["mint"]
        update_authority = info["owner"]
        hold_by_owner = int(info["tokenAmount"]["amount"]) > 0
        return dict(
            associate_account_pubkey=associate_account_pubkey,
            token_address=token_address,
            update_authority=update_authority,
            hold_by_owner=hold_by_owner,
        )

    def get_all_nft_accounts_by_owner(self, owner: str):
        owner = owner or self.keypair.public_key
        commitment: Commitment = Finalized
        encoding: str = "jsonParsed"
        opt = TokenAccountOpts(program_id=TOKEN_PROGRAM_ID, encoding=encoding)
        response = self.client.get_token_accounts_by_owner(PublicKey(owner), opt, commitment)
        return [self.parse_token_value(v) for v in response["result"]["value"]]

    def update_token_metadata(
        self, mint_address, max_retries=3, skip_confirmation=False, max_timeout=60, target=20, finalized=True, **kwargs
    ):
        """
        Updates the json metadata for a given mint token id
        """
        current_data = self.get_data(mint_address)
        data = dict(
            source_account=self.keypair,
            mint_address=PublicKey(mint_address),
            link=current_data.data.uri,
            name=kwargs.get("name", current_data.data.name),
            symbol=current_data.data.symbol,
            fee=current_data.data.seller_fee_basis_points,
            creators_addresses=current_data.data.creators,
            creators_verified=current_data.data.verified,
            creators_share=current_data.data.share,
        )
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
        resp["status"] = 200
        return json.dumps(resp)
