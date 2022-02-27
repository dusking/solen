Solen - A Solana Token Util
====
[![PypI](http://img.shields.io/pypi/v/solen.svg)](http://img.shields.io/pypi/v/solen.svg)


Solen is a base Python util for Solana based token commands. You can use it as a CLI tool and as a python library.

Features:
* Balance of local wallet for SOL / Token
* Transfer token to recipient wallet 
* Bulk token transfer to multiple recipients

Suggestions and PRs welcome!

[Latest Documentation](https://dusking.github.io/solen/).

**Note: This is experimental software for a young ecosystem. 
Use at your own risk. The author is not responsible for misuse of the software or for the user failing 
to test specific commands on devnet before using on production.**

See also: [the Solana tool suite](https://docs.solana.com/cli/install-solana-cli-tools), the official solana cli.

## Installation ##

To install the package you'll need to use pip. To install pip on ubuntu:

```
sudo apt update
sudo apt install python3-pip
sudo apt install python3.8-venv
```

Latest release installation using pip install (it's recommended to use python virtualenv):

```
python3 -m venv pyenv
source pyenv/bin/activate
pip install solen
```

To install from source, the latest in-progress version, you can clone the source and install using pip:

```
git clone git@github.com:dusking/solen.git
cd solen
git checkout main
pip install ./
```

## Config File ##

In addition to the package installation need to create a configuration file.
The location of the configuration file is: ~/.config/solen/config.ini


The configuration file should contain the following keys.
The token represent a specifc Solana based token for the token commands.
This is just a sample:

```
[endpoint]
dev = https://api.devnet.solana.com
main = https://api.mainnet-beta.solana.com

[addresses]
dev_token = 5YsymBWSdNiKWN5s8McLHw8toJLgZjhkx23gKgtWG2rZ
main_token = Fm9rHUTF5v3hwMLbStjZXqNBBoZyGriQaFM6sTFz3K8A

[solana]
default_env = dev
dev_keypair = ~/.config/solana/id.json
main_keypair = ~/.config/solana/id.json
```

## Usage ##

#### Env ####
The util perform actions on the Solana blockchain. 
Each command get env parameter that should be used to select the Solana RPC uri: dev or main.
The command will create Solana client on the relevant net, 
based on the node url in the configuration file. 


#### Balance ####

Get the current wallet SOL and Token balance, for example:

```
solen balance --env dev
```

#### Single Transfer ####

Transfer token from current wallet to a destination wallet.
A single transfer example: 

```
solen token transfer AuMtXeRS7hws6Ktw5R6tQq3LgDYE69HwwmG9kzNniScW 0.001
```

#### Bulk Transfer ####

You can run multiple transfers in a bulk, based on input CSV file contains all the transfers data.
The CSV should contain the following columns: wallet & amount. For example:

```csv
wallet,amount
7T6B6avexmB9pPRgjz6QvGLRkgNb5QeekJjz83KfWg41,0.356
Gwm9mtLoD4z2BBnGbEbB4Suu8eR62eMwSZsj5Ms6UUJ,0.445
```

The bulk transfer consists the followings steps:
* Init - prepare a json configuration file based on the given CSV file
* Dry Run - display the planned transfer add_commands
* Run - execute the transfer commands
* Confirm - verify that the transactions state is finalized

The commands are idempotent. You can run them multiple times. 
Running the transfer commands multiple times will run failed transactions if there are any.

Sample flow:

```
solen token bulk-transfer transfer-file-path.csv --skip_confirm --env dev
solen token bulk-transfer-status transfer-file-path.csv --env dev
```

