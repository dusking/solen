import argh

from solen import NFTClient

from .table import dict_to_pt, dicts_to_pt
from .log_print import LogPrint

log_print = LogPrint()


@argh.arg("-e", "--env", help="Solana env (dev / main)")
def accounts(env=None):
    """Display local wallet Token accounts"""
    log_print.header(f"get token balance (env: {env})")
    nft_client = NFTClient(env)
    account = nft_client.context.keypair.public_key
    log_print.info(f"NFT accounts for {account}")
    nft_accounts = nft_client.get_all_nft_accounts_by_owner()
    print(dicts_to_pt(nft_accounts, align="l"))


@argh.arg("mint_address", help="Mint address of NFT to modify")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
@argh.arg("-n", "--name", default=None, help="Solana env (dev / main)")
@argh.arg("-s", "--symbol", default=None, help="Solana env (dev / main)")
@argh.arg("-u", "--uri", default=None, help="Solana env (dev / main)")
def update(mint_address, env=None, **kwargs):
    """Update single NFT metadata"""
    log_print.header(f"Update NFT {mint_address} (env: {env})")
    update_data = dict(name=kwargs.get("name"), symbol=kwargs.get("symbol"), uri=kwargs.get("uri"))
    nft_client = NFTClient(env)
    update_response = nft_client.update_token_metadata(mint_address, **update_data)
    print(dict_to_pt(update_response, align="l"))


@argh.arg("csv", help="A csv file with wallet,amount to be transfer")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
@argh.arg("-d", "--dry-run", action="store_true", help="Dry run - don't send transactions")
@argh.arg("-s", "--skip_confirm", default=False, action="store_true", help="Run update without confirmations")
def bulk_update(csv, dry_run=False, env=None, skip_confirm=False):
    """Update multiple NFTs metadata, based on the content of the given csv"""
    log_print.header(f"bulk update NFT (skip-confirmation: {skip_confirm}, dry-run={dry_run}, env: {env})")
    nft_client = NFTClient(env)
    log_print.info(f"running on {nft_client.context.rpc_endpoint}")
    if nft_client.bulk_update_init(csv):
        nft_client.bulk_update_nft(csv, dry_run=dry_run, skip_confirm=skip_confirm)
        nft_client.bulk_confirm_transactions(csv)


@argh.arg("csv", help="A csv file with update actions data")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
def bulk_update_status(csv, env="dev"):
    """Confirm that bulk update transaction signatures are finalized"""
    log_print.header("bulk transfer confirm")
    nft_client = NFTClient(env)
    status_response = nft_client.get_update_status(csv)
    print(dict_to_pt(status_response, align="l"))
