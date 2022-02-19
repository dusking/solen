# pylint: disable=missing-docstring, unused-variable, no-self-use, invalid-name, broad-except
import argh
import logging

from solen import Solen

from .log_print import LogPrint
log_print = LogPrint()

loggerpy = logging.getLogger("solen")
loggerpy.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
loggerpy.addHandler(ch)


@argh.arg("-e", "--env", help="Solana env (dev / main)")
@argh.arg("-w", "--wallet", default=None, help="Wallet to receive the token balance for")
def balance(wallet=None, env=None):
    """
    Display local wallet balance of SOL & Token
    """
    log_print.header("get token balance")
    solen = Solen(env)
    wallet = wallet or solen.keypair.public_key
    log_print.info(f"get balance for: {wallet}")
    balance_sol = f"{solen.balance_sol(wallet):,}"
    balance_token = f"{solen.balance_token(wallet):,}"
    log_print.info(f"{balance_sol} SOL")
    log_print.info(f"{balance_token} Token")


@argh.arg("wallet", help="Wallet to receive the token")
@argh.arg("amount", help="Amount to transfer")
@argh.arg("-e", "--env", help="Solana env (dev / main)")
def transfer(wallet, amount, env=None):
    """
    Transfer token from local wallet ro recipient
    """
    log_print.header("transfer token")
    solen = Solen(env)
    solen.transfer_token(wallet, float(amount))


def main():
    from .bulk_transfer import init, run, confirm  # pylint: disable=import-outside-toplevel

    parser = argh.ArghParser(description="Solana Token Util (Solen)")
    parser.add_commands([balance, transfer])
    parser.add_commands([init, run, confirm], namespace="bulk-transfer")
    parser.dispatch()


if __name__ == "__main__":
    main()
