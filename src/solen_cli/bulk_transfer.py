import argh

from solen import TokenClient

from .table import dict_to_pt
from .log_print import LogPrint

log_print = LogPrint()


@argh.arg("csv", help="A csv file with wallet,amount to be transfer")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
def init(csv, env="dev"):
    """
    Create the required configuration for the bulk transfer run command
    """
    log_print.header("bulk transfer token init")
    token_client = TokenClient(env)
    token_client.bulk_transfer_token_init(csv)


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
def run(csv, dry_run=False, env=None, skip_confirm=False):
    """
    Transfer token to multiple addresses, based on the content of the given csv
    """
    log_print.header(f"bulk transfer token (skip-confirmation: {skip_confirm}, dry-run={dry_run})")
    token_client = TokenClient(env)
    log_print.info(f"running on {token_client.context.rpc_endpoint}")
    token_client.bulk_transfer_token(csv, dry_run=dry_run, skip_confirm=skip_confirm)


@argh.arg("csv", help="A csv file with wallet,amount to be transfer")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
def confirm(csv, env="dev"):
    """
    Confirm that transfer amount transaction signatures are finalized
    """
    log_print.header("bulk transfer confirm")
    token_client = TokenClient(env)
    token_client.bulk_confirm_transactions(csv)


@argh.arg("csv", help="A csv file with wallet,amount to be transfer")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
def status(csv, env="dev"):
    """
    Confirm that transfer amount transaction signatures are finalized
    """
    log_print.header("bulk transfer confirm")
    token_client = TokenClient(env)
    status_response = token_client.get_transfer_status(csv)
    print(dict_to_pt(status_response, align="l"))
