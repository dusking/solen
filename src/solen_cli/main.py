# pylint: disable=missing-docstring, unused-variable, no-self-use, invalid-name, broad-except
import logging

import argh
import pkg_resources

# from solen import Context, NFTClient, SOLClient, TokenClient

from .log_print import LogPrint
from .token import balance, transfer, bulk_transfer, bulk_status

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


def main():
    parser = argh.ArghParser(description="Solana Token Util (Solen)")
    parser.add_commands([version])
    parser.add_commands([balance, transfer, bulk_transfer, bulk_status], namespace="token")
    parser.dispatch()


if __name__ == "__main__":
    main()
