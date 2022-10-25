import json, telebot, os
from dotenv import load_dotenv, find_dotenv
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from typing import List, Optional, Union
from ape import Contract, chain, project
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
bot = telebot.TeleBot(telegram_bot_key)

CHAT_IDS = {
    "WAVEY_ALERTS": "-789090497",
    "CURVE_WARS": "-1001712241544",
    "GNOSIS_CHAIN_POC": "-1001516144118"
}

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

    alert_ycrv(last_block, current_block)
    alert_seasolver(last_block, current_block)
    

    data['last_block'] = current_block
    with open("local_data.json", 'w') as fp:
        json.dump(data, fp, indent=2)
    
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
    alert_size_threshold = 150_000e18
    start = max(last_block, deploy_block)

    ycrv = Contract('0xFCc5c47bE19d06BF83eB04298b026F81069ff65b')
    prod_logs = list(settlement.Settlement.range(start, current_block, search_topics={'solver': prod_solver}))
    barn_logs = list(settlement.Settlement.range(start, current_block, search_topics={'solver': barn_solver}))
    logs = prod_logs + barn_logs
    for l in logs:
        txn_hash = l.transaction_hash
        solver = l.dict()['event_arguments']['solver']
        block = l.block_number
        trades = enumerate_trades(block, txn_hash)
        format_solver_alert(solver, txn_hash, block, trades)

def enumerate_trades(block, txn_hash):
    settlement = Contract('0x9008d19f58aabd9ed0d60971565aa8510560ab41')
    logs = list(settlement.Trade.range(block-1, block+1))
    trades = []
    
    for l in logs:
        if l.transaction_hash != txn_hash:
            continue
        args = l.dict()['event_arguments']
        eth = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
        trade = {
            'owner': args['owner'],
            'sell_token_address': args['sellToken'],
            'sell_token_symbol': 'ETH' if args['sellToken'] == eth else project.ERC20.at(args['sellToken']).symbol(),
            'sell_token_decimals': 18 if args['sellToken'] == eth else project.ERC20.at(args['sellToken']).decimals(),
            'buy_token_address': args['buyToken'],
            'buy_token_symbol': 'ETH' if args['buyToken'] == eth else project.ERC20.at(args['buyToken']).symbol(),
            'buy_token_decimals': 18 if args['buyToken'] == eth else project.ERC20.at(args['buyToken']).decimals(),
            'sell_amount': args['sellAmount'],
            'buy_amount': args['buyAmount'],
            'fee_amount': args['feeAmount'],
            'order_uid': '0x'+args['orderUid'].hex(),
        }
        trades.append(trade)
    return trades

def format_solver_alert(solver, txn_hash, block, trade_data):
    prod_solver = '0x398890BE7c4FAC5d766E1AEFFde44B2EE99F38EF'
    etherscan_base_url = f'https://etherscan.io/'
    cow_explorer_url = f'https://explorer.cow.fi/orders/{trade_data[0]["order_uid"]}'
    cow_explorer_url = f'https://explorer.cow.fi/tx/{txn_hash}'
    
    ts = chain.blocks[block].timestamp
    dt = datetime.utcfromtimestamp(ts).strftime("%m/%d %H:%M")
    msg = f'{"🧜‍♂️" if solver == prod_solver else "🐬"} *New solve detected!*\n'
    msg += f'by [{solver[0:7]}...]({etherscan_base_url}address/{solver})   {dt}\n\n'
    msg += f'📕 *Trades*:\n'
    for t in trade_data:
        user = t["owner"]
        msg += f'    User: [{user[0:7]}...]({etherscan_base_url}address/{user})\n'
        sell_amt = round(t["sell_amount"]/10**t["sell_token_decimals"],4)
        buy_amt = round(t["buy_amount"]/10**t["buy_token_decimals"],4)
        msg += f'    [{t["sell_token_symbol"]}]({etherscan_base_url}token/{t["sell_token_address"]}) {sell_amt:,} --> [{t["buy_token_symbol"]}]({etherscan_base_url}token/{t["buy_token_address"]}) {buy_amt:,}\n\n'
    msg += f'\n🔗 [Etherscan]({etherscan_base_url}tx/{txn_hash}) | [Cow Explorer]({cow_explorer_url})'
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