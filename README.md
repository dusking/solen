Tiny Transfer
====

This is a Solana Py wrapper for token transfer.


**Note: This is experimental software for a young ecosystem. 
Use at your own risk. The author is not responsible for misuse of the software or for the user failing 
to test specific commands on devnet before using on production.**

## Setup ##

Installation is via pip install. 
In addition to the package installation need to create a configuration file.
The location of the configuration file is: ~/.tiny/config.ini


The configuration file should contain the following keys.
The token represent a specifc Solana based token for the token commands.
This is just a sample:

```
[RPC]
dev = https://api.devnet.solana.com
main = https://api.mainnet-beta.solana.com

[addresses]
token = 5YsymBWSdNiKWN5s8McLHw8toJLgZjhkx23gKgtWG2rZ

[solana]
keypair = ~/.config/solana/id.json
```

## Usage ##

#### Env ####
The util perform actions on the Solana blockchain. 
Each command get env parameter - dev or main.
The command will create Solana client on the relevant net, 
based on the node url in the configuration file. 


#### Balance ####

Get the current wallet SOL and Token balance, for example:

```
tiny balance dev
```

#### Transfer Token ####

Transfer token from current wallet to a destination wallet.
A single transfer example: 

```
tiny transfer-token dev AuMtXeRS7hws6Ktw5R6tQq3LgDYE69HwwmG9kzNniScW 0.001
```

To run multiple transfers, need to create a csv file with the wanted transfers,
with wallet & amount columns. For example:

```csv
wallet,amount
7T6B6avexmB9pPRgjz6QvGLRkgNb5QeekJjz83KfWg41,0.356
Gwm9mtLoD4z2BBnGbEbB4Suu8eR62eMwSZsj5Ms6UUJ,0.445
```

Then need to call the following command:

```
tiny bulk-transfer-token dev transfer-file-path.csv
```

The first run will create a processing json file under the ~/.tiny folder.
In case there are transfer failures and you want to re-run the failures commands,
neet to run the command again with the `--continue` parameter:

```
tiny bulk-transfer-token dev transfer-file-path.csv -c
```

After you run the transfer you have the signatures in the processing file.
To verify that all the positions are in Finalized state, need to run:

```
tiny bulk-transfer-confirm transfer-file-path.csv
```
