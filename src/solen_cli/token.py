import argh

from solen import TokenClient, Context

from .table import dict_to_pt
from .log_print import LogPrint

log_print = LogPrint()


@argh.arg("-e", "--env", help="Solana env (dev / main)")
def balance(env=None):
    """
    Display local wallet balance of SOL & Token
    """
    log_print.header("get token balance")
    context = Context(env)
    wallet = context.keypair.public_key
    token_client = TokenClient(env, context=context)
    registered_info = token_client.get_registered_info()
    token_symbol = registered_info[0].symbol if registered_info else "N/A"
    balance_info = {
        "account address": wallet,
        "token mint": token_client.token_mint,
        "token symbol": token_symbol,
        "amount": token_client.balance()
    }
    print(dict_to_pt(balance_info, align="l"))


@argh.arg("wallet", help="Wallet to receive the token")
@argh.arg("amount", help="Amount to transfer")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
def transfer(wallet, amount, env=None):
    """
    Transfer token from local wallet ro recipient
    """
    log_print.header("transfer token")
    token_client = TokenClient(env)
    token_client.transfer_token(wallet, float(amount))


@argh.arg("csv", help="A csv file with wallet,amount to be transfer")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
@argh.arg("-d", "--dry-run", action="store_true", help="Dry run - don't send transactions")
@argh.arg(
    "-s",
    "--skip_confirm",
    default=False,
    action="store_true",
    help="Run transaction without confirmations - to make it faster",
)


def bulk_transfer(csv, dry_run=False, env=None, skip_confirm=False):
    """
    Transfer token to multiple addresses, based on the content of the given csv
    """
    log_print.header(f"bulk transfer token (skip-confirmation: {skip_confirm}, dry-run={dry_run})")
    token_client = TokenClient(env)
    log_print.info(f"running on {token_client.context.rpc_endpoint}")
    if token_client.bulk_transfer_token_init(csv):
        token_client.bulk_transfer_token(csv, dry_run=dry_run, skip_confirm=skip_confirm)
        token_client.bulk_confirm_transactions(csv)


@argh.arg("csv", help="A csv file with wallet,amount to be transfer")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
def bulk_status(csv, env="dev"):
    """
    Confirm that transfer amount transaction signatures are finalized
    """
    log_print.header("bulk transfer confirm")
    token_client = TokenClient(env)
    status_response = token_client.get_transfer_status(csv)
    print(dict_to_pt(status_response, align="l"))
