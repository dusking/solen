CLI
===

Overview
^^^^^^^^

This CLI aim to expose basic RPC commands for a Solana based Token as simple CLI.

Features:

* Balance of local wallet for SOL / Token
* Transfer token to recipient wallet
* Bulk token transfer to multiple recipients

Need to verify you first follow the :ref:`installation <index:installation>`
and :ref:`configuration file <index:config file>` steps.

Basic
^^^^^

The util perform actions on the Solana blockchain.
Each command get env parameter that should be used to select the Solana RPC uri: dev or main.
The command will create Solana client on the relevant net,
based on the node url in the configuration file.

Balance
^^^^^^^

Get the current wallet SOL and Token balance, for example:

.. highlight:: sh
.. code-block:: sh

    solen balance --env dev


Transfer
^^^^^^^^

Single Transfer
---------------

Transfer token from current wallet to a destination wallet.
A single transfer example:

.. highlight:: sh
.. code-block:: sh

    solen transfer AuMtXeRS7hws6Ktw5R6tQq3LgDYE69HwwmG9kzNniScW 0.001


Bulk Transfer
-------------

You can run multiple transfers in a bulk, based on input CSV file contains all the transfers data.
The CSV should contain the following columns: wallet & amount. For example:

.. highlight:: sh
.. code-block:: sh

    wallet,amount
    7T6B6avexmB9pPRgjz6QvGLRkgNb5QeekJjz83KfWg41,0.356
    Gwm9mtLoD4z2BBnGbEbB4Suu8eR62eMwSZsj5Ms6UUJ,0.445

The bulk transfer consists the followings steps:

* Init - prepare a json configuration file based on the given CSV file
* Dry Run - display the planned transfer add_commands
* Run - execute the transfer commands
* Confirm - verify that the transactions state is finalized

The commands are idempotent. You can run them multiple times.
Running the transfer commands multiple times will run failed transactions if there are any.
The bulk-transfer skip-confirm option will make the run faster, but will may reduce the live status reliability.

Sample flow:

.. highlight:: sh
.. code-block:: sh

    solen bulk-transfer -h
    solen bulk-transfer init transfer-file-path.csv --env dev
    solen bulk-transfer run transfer-file-path.csv --env dev --dry-run
    solen bulk-transfer run transfer-file-path.csv --env dev --skip-confirm
    solen bulk-transfer confirm transfer-file-path.csv --env dev
