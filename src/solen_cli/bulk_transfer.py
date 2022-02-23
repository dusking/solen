import argh

from solen import TokenClient

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
def run(csv, dry_run=False, env=None):
    """
    Transfer token to multiple addresses, based on the content of the given csv
    """
    log_print.header(f"bulk transfer token (dry-run={dry_run})")
    token_client = TokenClient(env)
    token_client.bulk_transfer_token(csv, dry_run=dry_run)


@argh.arg("csv", help="A csv file with wallet,amount to be transfer")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
def confirm(csv, env="dev"):
    """
    Confirm that transfer amount transaction signatures are finalized
    """
    log_print.header("bulk transfer confirm")
    token_client = TokenClient(env)
    token_client.bulk_confirm_transactions(csv)
