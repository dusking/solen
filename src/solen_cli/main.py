# pylint: disable=missing-docstring, unused-variable, no-self-use, invalid-name, broad-except
import logging

import argh
import pkg_resources

from solen import Context, NFTClient, SOLClient, TokenClient

from .log_print import LogPrint
from .bulk_transfer import run, init, confirm, status

log_print = LogPrint()

loggerpy = logging.getLogger("solen")
loggerpy.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
loggerpy.addHandler(ch)


def version():
    """
    Current installed version
    """
    log_print.info(pkg_resources.require("solen")[0].version)


@argh.arg("-e", "--env", help="Solana env (dev / main)")
def balance(env=None):
    """
    Display local wallet balance of SOL & Token
    """
    log_print.header("get token balance")
    context = Context(env)
    wallet = context.keypair.public_key
    log_print.info(f"get balance for: {wallet}")
    log_print.info(f"{SOLClient(env, context=context).balance():,} SOL")
    token_client = TokenClient(env, context=context)
    registered_info = token_client.get_registered_info()
    token_symbol = registered_info[0].symbol if registered_info else token_client.token_mint
    log_print.info(f"{token_client.balance()} {token_symbol}")


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


def main():
    parser = argh.ArghParser(description="Solana Token Util (Solen)")
    parser.add_commands([version, balance, transfer])
    parser.add_commands([init, run, confirm, status], namespace="bulk-transfer")
    parser.dispatch()


if __name__ == "__main__":
    main()
