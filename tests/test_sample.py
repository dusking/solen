from solen import Solen


def test_env():
    solen = Solen("dev")
    assert solen.rpc == "https://api.devnet.solana.com"
