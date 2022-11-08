import json, telebot, os, time
from dotenv import load_dotenv, find_dotenv
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from typing import List, Optional, Union
from ape import Contract, chain, project, networks
from ape.api import ReceiptAPI
from ape.types import AddressType, ContractLog
from ape.utils import ManagerAccessMixin
from ape_tokens import tokens
from ape_tokens.managers import ERC20
from eth_abi.packed import encode_abi_packed
from eth_utils import keccak
from datetime import datetime, timezone

load_dotenv(find_dotenv())
telegram_bot_key = os.environ.get('WAVEY_ALERTS_BOT_KEY')
alerts_enabled = True if os.environ.get('ENVIRONMENT') == "PROD" else False
etherscan_base_url = f'https://etherscan.io/'
bot = telebot.TeleBot(telegram_bot_key)
oracle = project.ORACLE.at('0x83d95e0D5f402511dB06817Aff3f9eA88224B030')
barn_solver = '0x8a4e90e9AFC809a69D2a3BDBE5fff17A12979609'
prod_solver = '0x398890BE7c4FAC5d766E1AEFFde44B2EE99F38EF'
trade_handler = '0xcADBA199F3AC26F67f660C89d43eB1820b7f7a3b'
address_list = [prod_solver, barn_solver]

CHAT_IDS = {
    "WAVEY_ALERTS": "-789090497",
    "CURVE_WARS": "-1001712241544",
    "GNOSIS_CHAIN_POC": "-1001516144118",
    "YBRIBE": "-1001862925311",
}

SKIP_LIST = [
    '0xB4b9DC1C77bdbb135eA907fd5a08094d98883A35'
]

def main():
    # last_block
    with open("local_data.json", "r") as jsonFile:
        data = json.load(jsonFile)
        last_block = data['last_block']
    if not last_block:
        last_block = 15_000_000
    print(f'Starting from block number {last_block}')
    current_block = chain.blocks.height
    data['last_block'] = current_block

    alert_bribes(last_block, current_block)
    alert_ycrv(last_block, current_block)
    alert_seasolver(last_block, current_block)
    find_reverts(address_list, last_block-1, current_block)

    data['last_block'] = current_block
    with open("local_data.json", 'w') as fp:
        json.dump(data, fp, indent=2)


def alert_bribes(last_block, current_block):
    deploy_block = 15_878_262
    start = max(last_block, deploy_block)
    ybribe = Contract('0x03dFdBcD4056E2F92251c7B07423E1a33a7D3F6d')
    logs = list(ybribe.RewardAdded.range(start, current_block))
    for l in logs:
        args = l.dict()['event_arguments']
        txn_hash = l.transaction_hash
        briber = args['briber']
        gauge = args['gauge']
        token = Contract(args['reward_token'])
        amount = args['amount']
        fee = args['fee']
        gauge_name = ''
        abbr, link, markdown = abbreviate_address(briber)
        briber = markdown
        try:
            gauge_name = Contract(gauge).name()
        except:
            pass
        amt = round(amount/10**token.decimals(),2)
        fee = round(fee/10**token.decimals(),2)
        msg = f'🤑 *New Bribe Add Detected!*'
        msg += f'\n\n*Amount*: {amt:,} {token.symbol()}'
        msg += f'\n*Gauge*: {gauge_name} {markdown}'
        msg += f'\n*Briber*: {briber}'
        msg += f'\n*Fee*: {fee:,} {token.symbol()}'
        msg += f'\n\n🔗 [View on Etherscan](https://etherscan.io/tx/{txn_hash})'
        chat_id = CHAT_IDS["WAVEY_ALERTS"]
        if alerts_enabled:
            chat_id = CHAT_IDS["YBRIBE"]
        bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

    # logs = list(ybribe.RewardClaimed.range(start, current_block))
    # for l in logs:
    #     args = l.dict()['event_arguments']
    #     txn_hash = l.transaction_hash
    #     user = args['user']
    #     gauge = args['gauge']
    #     # token = Contract(args['reward_token'])
    #     amount = args['amount']

    #     gauge_name = ''
    #     abbr, link, markdown = abbreviate_address(user)
    #     user = markdown
    #     abbr, link, markdown = abbreviate_address(gauge)
    #     gauge = markdown
    #     try:
    #         gauge_name = Contract(gauge).name()
    #     except:
    #         pass
    #     amt = round(amount/10**18,2)
    #     msg = f'💰 *Bribe Claim Detected!*'
    #     msg += f'\n\n*Amount*: {amt:,}'# {token.symbol()}'
    #     msg += f'\n*Gauge*: {gauge_name} {gauge}'
    #     msg += f'\n*User*: {user}'
    #     msg += f'\n\n🔗 [View on Etherscan](https://etherscan.io/tx/{txn_hash})'
    #     chat_id = CHAT_IDS["WAVEY_ALERTS"]
    #     if alerts_enabled:
    #         chat_id = CHAT_IDS["YBRIBE"]
    #     bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

def alert_ycrv(last_block, current_block):
    # Config
    deploy_block = 15_624_808
    alert_size_threshold = 150_000e18
    start = max(last_block, deploy_block)
    ycrv = Contract('0xFCc5c47bE19d06BF83eB04298b026F81069ff65b')
    logs = list(ycrv.Mint.range(start, current_block))

    for l in logs:
        args = l.dict()['event_arguments']
        value = args['value']
        minter = args['minter']
        receiver = args['receiver']
        if value > alert_size_threshold:
            block = l.block_number
            ts = chain.blocks[block].timestamp
            txn_hash = l.transaction_hash
            dt = datetime.utcfromtimestamp(ts).strftime("%m/%d/%Y, %H:%M:%S")
            abbr, link, markdown = abbreviate_address(receiver)
            msg = f'✨ *YCRV mint detected!*\n\n'
            msg += f'User: {markdown}\n\n'
            amt = round(value/1e18,2)
            burned = args["burned"]
            if burned:
                msg += f'{amt:,} yveCRV migrated'
            else:
                msg += f'{amt:,} CRV locked'
            msg += f'\n\n🔗 [Etherscan](https://etherscan.io/tx/{txn_hash})'

            chat_id = CHAT_IDS["WAVEY_ALERTS"]
            if alerts_enabled:
                chat_id = CHAT_IDS["CURVE_WARS"]
            bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

def alert_seasolver(last_block, current_block):
    barn_solver = '0x8a4e90e9AFC809a69D2a3BDBE5fff17A12979609'
    prod_solver = '0x398890BE7c4FAC5d766E1AEFFde44B2EE99F38EF'
    settlement = Contract('0x9008d19f58aabd9ed0d60971565aa8510560ab41')

    # Config
    deploy_block = 15_624_808
    start = max(last_block, deploy_block)

    prod_logs = list(settlement.Settlement.range(start, current_block, search_topics={'solver': prod_solver}))
    barn_logs = list(settlement.Settlement.range(start, current_block, search_topics={'solver': barn_solver}))
    logs = prod_logs + barn_logs
    for l in logs:
        txn_hash = l.transaction_hash
        solver = l.dict()['event_arguments']['solver']
        block = l.block_number
        trades = enumerate_trades(block, txn_hash)
        slippage = calculate_slippage(trades, block)
        format_solver_alert(solver, txn_hash, block, trades, slippage)

def calculate_slippage(trades, block):

    ret = {}
    for trade in trades:
        buy_token_address = trade['buy_token_address']

        # If there is a trade for eth, use weth instead since TH will never
        # get native eth
        if buy_token_address.lower() == "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE".lower():
            buy_token_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

        # we might have calculated the slippage previously
        if buy_token_address in ret:
            continue

        buy_token = project.ERC20.at(buy_token_address)
        before = buy_token.balanceOf(trade_handler, block_identifier=block-1)
        after = buy_token.balanceOf(trade_handler, block_identifier=block+1)
        ret[buy_token_address] = before-after

    return ret


def enumerate_trades(block, txn_hash):
    settlement = Contract('0x9008d19f58aabd9ed0d60971565aa8510560ab41')
    logs = list(settlement.Trade.range(block-1, block+1))
    trades = []
    for l in logs:
        if l.transaction_hash != txn_hash:
            continue
        args = l.dict()['event_arguments']
        eth = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
        try:
            sell_token = args['sellToken']
            if sell_token == eth:
                sell_token_symbol = 'ETH'
                sell_token_decimals = 18
            else:
                sell_token_symbol = project.ERC20.at(sell_token).symbol()
                sell_token_decimals = project.ERC20.at(sell_token).decimals()
        except:
            sell_token_symbol = '? Cannot Find ?'
            sell_token_decimals = 18

        try:
            buy_token = args['buyToken']
            if buy_token == eth:
                buy_token_symbol = 'ETH'
                buy_token_decimals = 18
            else:
                buy_token_symbol = project.ERC20.at(buy_token).symbol()
                buy_token_decimals = project.ERC20.at(buy_token).decimals()
        except:
            buy_token_symbol = '? Cannot Find ?'
            buy_token_decimals = 18

        trade = {
            'owner': args['owner'],
            'sell_token_address': args['sellToken'],
            'sell_token_symbol': sell_token_symbol,
            'sell_token_decimals': sell_token_decimals,
            'buy_token_address': args['buyToken'],
            'buy_token_symbol': buy_token_symbol,
            'buy_token_decimals': buy_token_decimals,
            'sell_amount': args['sellAmount'],
            'buy_amount': args['buyAmount'],
            'fee_amount': args['feeAmount'],
            'order_uid': '0x'+args['orderUid'].hex(),
        }
        trades.append(trade)
    return trades

def format_solver_alert(solver, txn_hash, block, trade_data, slippage):
    prod_solver = '0x398890BE7c4FAC5d766E1AEFFde44B2EE99F38EF'
    cow_explorer_url = f'https://explorer.cow.fi/orders/{trade_data[0]["order_uid"]}'
    cow_explorer_url = f'https://explorer.cow.fi/tx/{txn_hash}'
    txn_receipt = networks.provider.get_receipt(txn_hash)

    ts = chain.blocks[block].timestamp
    dt = datetime.utcfromtimestamp(ts).strftime("%m/%d %H:%M")
    msg = f'{"🧜‍♂️" if solver == prod_solver else "🐓"} *New solve detected!*\n'
    msg += f'by [{solver[0:7]}...]({etherscan_base_url}address/{solver})  @ {dt}\n\n'
    msg += f'📕 *Trade(s)*:\n'
    for t in trade_data:
        user = t["owner"]
        sell_amt = round(t["sell_amount"]/10**t["sell_token_decimals"],4)
        buy_amt = round(t["buy_amount"]/10**t["buy_token_decimals"],4)
        msg += f'    [{t["sell_token_symbol"]}]({etherscan_base_url}token/{t["sell_token_address"]}) {sell_amt:,} --> [{t["buy_token_symbol"]}]({etherscan_base_url}token/{t["buy_token_address"]}) {buy_amt:,} | [{user[0:7]}...]({etherscan_base_url}address/{user})\n'
    msg += f'\n{calc_gas_cost(txn_receipt)}'
    msg += f'\n\n🔗 [Etherscan]({etherscan_base_url}tx/{txn_hash}) | [Cow Explorer]({cow_explorer_url})'

    # Add slippage info
    msg += "\n ✂️ Trade handler Slippage ✂️"
    for key in slippage:
        token = project.ERC20.at(key)
        slippage = slippage[key]
        color = 🔴 if slippage < 0 else 🟢
        amount = round(slippage/10**token.decimals(),4)
        msg += f"\n  {color} {token.symbol()}: {amount}"

    if alerts_enabled:
        chat_id = CHAT_IDS["GNOSIS_CHAIN_POC"]
    else:
        chat_id = CHAT_IDS["WAVEY_ALERTS"]
    bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

def abbreviate_address(address):
    abbr = address[0:7]
    link = f'https://etherscan.io/address/{address}'
    markdown = f'[{abbr}...]({link})'
    return abbr, link, markdown

def find_reverts(address_list, start_block, end_block):
    for b in range(start_block, end_block):
        block = chain.blocks[b]
        for t in block.transactions:
            if t.dict()['from'] in address_list:
                txn_hash = t.txn_hash.hex()
                txn_receipt = networks.provider.get_receipt(txn_hash)
                failed = txn_receipt.failed
                if not failed:
                    continue
                msg = f'*🤬  Failed Transaction detected!*\n\n'
                f= t.dict()['from']
                e = "🧜‍♂️" if f == address_list[0] else "🐓"
                abbr, link, markdown = abbreviate_address(f)
                msg += f'Sent from {markdown} {e}\n\n'
                msg += f'{calc_gas_cost(txn_receipt)}'
                msg += f'\n\n🔗 [Etherscan]({etherscan_base_url}tx/{txn_hash}) | [Tenderly](https://dashboard.tenderly.co/tx/mainnet/{txn_hash})'
                if alerts_enabled:
                    chat_id = CHAT_IDS["GNOSIS_CHAIN_POC"]
                else:
                    chat_id = CHAT_IDS["WAVEY_ALERTS"]
                bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

def calc_gas_cost(txn_receipt):
    eth_used = txn_receipt.gas_price * txn_receipt.gas_used
    gas_cost = oracle.getNormalizedValueUsdc('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', eth_used) / 10**6
    return f'💸 ${round(gas_cost,2):,} | {round(eth_used/1e18,4)} ETH'
