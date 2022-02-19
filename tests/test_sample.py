from tiny_solana import TinySolana


def test_env():
    tiny_solana = TinySolana("dev")
    assert tiny_solana.rpc == "https://api.devnet.solana.com"
