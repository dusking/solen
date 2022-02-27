.. solen documentation master file, created by
   sphinx-quickstart on Tue Feb 22 17:43:11 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Introduction
============

.. image:: https://img.shields.io/pypi/v/solen?color=blue
   :alt: PyPI version
   :target: https://pypi.org/project/solen/

.. image:: https://img.shields.io/badge/License-MIT-yellow.svg
   :alt: License
   :target: https://github.com/dusking/solen/blob/main/LICENSE

Solen is a base Python util for Solana based token commands.
You can use it as a CLI tool and as a python library.
It's based on the `Solana.py package <https://github.com/michaelhly/solana-py>`_
and on the `Solana JSON RPC <https://docs.solana.com/developing/clients/jsonrpc-api/>`_.

Python Library Features:

* Handle token instructions
* Handle NFT instructions

CLI Features:

* Balance for configured token and NFTs for local wallet.
* Transfer token to recipient wallet.
* Bulk token transfer to multiple recipients.
* NFT update.
* Bulk NFT update.

Suggestions and PRs welcome!

.. note::
   This is experimental software for a young ecosystem.
   Use at your own risk. The author is not responsible for misuse of the software or for the user failing
   to test specific commands on devnet before using on production.

See also: [the Solana tool suite](https://docs.solana.com/cli/install-solana-cli-tools), the official solana cli.

.. _installation:

Installation
------------

To install the package you'll need to use pip. To install pip on ubuntu:

.. highlight:: sh
.. code-block:: sh

   sudo apt update
   sudo apt install python3-pip
   sudo apt install python3.8-venv

It's recommended to use python virtualenv, to install virtualenv:

.. highlight:: sh
.. code-block:: sh

   python3 -m venv pyenv
   source pyenv/bin/activate

Latest release installation using pip install:

.. highlight:: sh
.. code-block:: sh

   pip install solen

.. _config file:

Config File
-----------

In addition to the package installation need to create a configuration file.
The location of the configuration file is: ~/.config/solen/config.ini

The endpoint section contains keys with rpc endpoints. Those keys represent the optional env values
that can be used in Solen objects. In the following example there are 2 optional env values: dev and main.
Based on the env value the relevant configuration will be used for: endpoint, token address and keypair.

This is just a sample for a configuration file:

.. highlight:: sh
.. code-block:: sh

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


Usage as CLI
----------------

General usage:

The util perform actions on the Solana blockchain.
Each command get env parameter that should be used to select the Solana RPC uri: dev or main.
The command will create Solana client on the relevant net,
based on the node url in the configuration file.

To get the current wallet balance:

.. highlight:: sh
.. code-block:: sh

   solen balance --env dev

To perform a single transfer from current wallet to a destination wallet.

.. highlight:: sh
.. code-block:: sh

   solen token transfer AuMtXeRS7hws6Ktw5R6tQq3LgDYE69HwwmG9kzNniScW 0.001

You can run multiple transfers in a bulk, based on input CSV file contains all the transfers data.
The CSV should contain the following columns: wallet & amount. For example:

.. highlight:: sh
.. code-block:: sh

   solen bulk-transfer -h
   solen token bulk-transfer transfer-file-path.csv --skip_confirm --env dev
   solen token bulk-transfer-status transfer-file-path.csv --env dev

Usage as Library
----------------

You can use the Solen library to perform actions related to NFT & Tokens.
For examples and more details you can read the Solen Library section,
there are the :ref:`NFT Client <solen:nft client>`
and the :ref:`Token Client <solen:token client>` sectoins.


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   self
   solen
   cli


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
