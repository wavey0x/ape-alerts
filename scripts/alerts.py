import json, telebot, os, time
from dotenv import load_dotenv, find_dotenv
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from typing import List, Optional, Union
from ape import Contract, chain, project, networks, convert
from ape.api import ReceiptAPI
from ape.types import AddressType, ContractLog
from ape.utils import ManagerAccessMixin
from ape_tokens import tokens
from ape_tokens.managers import ERC20
from eth_abi.packed import encode_abi_packed
from eth_utils import keccak, humanize_seconds
from datetime import datetime, timezone

load_dotenv(find_dotenv())
telegram_bot_key = os.environ.get('WAVEY_ALERTS_BOT_KEY')
alerts_enabled = True if os.environ.get('ENVIRONMENT') == "PROD" else False
etherscan_base_url = f'https://etherscan.io/'
bot = telebot.TeleBot(telegram_bot_key)
oracle = project.ORACLE.at('0x83d95e0D5f402511dB06817Aff3f9eA88224B030')
barn_solver = '0x8a4e90e9AFC809a69D2a3BDBE5fff17A12979609'
prod_solver = '0x398890BE7c4FAC5d766E1AEFFde44B2EE99F38EF'
trade_handler = '0xb634316E06cC0B358437CbadD4dC94F1D3a92B3b' #'0xcADBA199F3AC26F67f660C89d43eB1820b7f7a3b'
address_list = [prod_solver, barn_solver]

YFI_LOCKERS = {
    '0xF750162fD81F9a436d74d737EF6eE8FC08e98220': 'StakeDAO',
}

CHAT_IDS = {
    "WAVEY_ALERTS": "-789090497",
    "CURVE_WARS": "-1001712241544",
    "GNOSIS_CHAIN_POC": "-1001516144118",
    "YBRIBE": "-1001862925311",
    "VEYFI": "-1001558128423",
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
    alert_veyfi_lock(last_block, current_block)
    alert_fee_distributor(last_block, current_block)
    alert_bribes(last_block, current_block)
    alert_ycrv(last_block, current_block)
    alert_seasolver(last_block, current_block)
    find_reverts(address_list, last_block, current_block)

    data['last_block'] = current_block
    with open("local_data.json", 'w') as fp:
        json.dump(data, fp, indent=2)

def alert_veyfi_lock(last_block, current_block):
    import code
    deploy_block = 15_974_608
    veyfi = Contract('0x90c1f9220d90d3966FbeE24045EDd73E1d588aD5')
    start = max(last_block, deploy_block)
    logs = list(veyfi.Supply.range(start, current_block))
    receipts = []
    for l in logs:
        txn_hash = l.transaction_hash
        txn_receipt = networks.provider.get_receipt(txn_hash)
        if txn_receipt not in receipts:
            receipts.append(txn_receipt)
        

    for r in receipts:
        supply_logs = r.decode_logs([veyfi.Supply])
        modify_logs = r.decode_logs([veyfi.ModifyLock])
        for s in supply_logs:
            block = l.block_number
            ts = chain.blocks[block].timestamp
            txn_hash = l.transaction_hash
            txn_receipt = networks.provider.get_receipt(txn_hash)
            idx = 0
            args = s.dict()['event_arguments']
            old_supply = args['old_supply']
            new_supply = args['new_supply']
            # code.interact(local=locals())
            try:
                user = list(modify_logs)[idx]['user']
            except:
                continue
            amount = new_supply - old_supply
            idx += 1
            if amount == 0:
                continue
            elif amount > 0:
                # New user?
                new_user = veyfi.balanceOf(user, block_identifier=block-1) == 0
                locked_end = veyfi.locked(user,block_identifier=block)['end']
                locked_amount = veyfi.locked(user,block_identifier=block)['amount']/1e18
                balance = veyfi.balanceOf(user,block_identifier=block)/1e18
                current_time = chain.blocks[block].timestamp
                remaining = locked_end - current_time
                abbr, link, markdown = abbreviate_address(user)
                msg = f'🔒 *veYFI Deposit Detected!*\n\n'
                msg += f'Supply increase: {round(amount/1e18,3):,} YFI\n\n'
                msg += f'User: {markdown} {"🆕" if new_user else ""}\n'
                msg += f'Balance: {round(balance,3):,} veYFI\n'
                msg += f'Locked: {round(locked_amount,3):,} YFI\n'
                msg += f'Lock time remaining: {humanize_seconds(remaining)}'
                msg += f'\n\n🔗 [View on Etherscan](https://etherscan.io/tx/{txn_hash})'
                chat_id = CHAT_IDS["WAVEY_ALERTS"]
                if alerts_enabled:
                    chat_id = CHAT_IDS["VEYFI"]
                bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)
            else:
                new_user = veyfi.balanceOf(user, block_identifier=block-1) == 0
                locked_end = veyfi.locked(user,block_identifier=block)['end']
                current_time = chain.blocks.head.timestamp
                remaining = locked_end - current_time
                abbr, link, markdown = abbreviate_address(user)
                msg = f'🔓 *veYFI Withdraw Detected!*\n\n'
                msg += f'User: {markdown}\n'
                msg += f'Supply decrease: {round(amount/1e18,2):,} YFI'
                msg += f'\n\n🔗 [View on Etherscan](https://etherscan.io/tx/{txn_hash})'
                chat_id = CHAT_IDS["WAVEY_ALERTS"]
                if alerts_enabled:
                    chat_id = CHAT_IDS["VEYFI"]
                bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

        # if len(supply_logs) > 0 and len(modify_logs) == len(supply_logs):
        #     idx = len(supply_logs)-1
        #     s = supply_logs[idx]
        #     s['event_arguments']
        #     old_supply = args['old_supply']
        #     new_supply = args['new_supply']
        # penalty_logs = txn_receipt.decode_logs([veyfi.Penalty])
        # withdraw_logs = txn_receipt.decode_logs([veyfi.Withdraw])

        # modify_logs[0]
        #     print(l)
        #     user = 
        # print(txn_receipt.events)
        # s.dict()['event_arguments']
        # old_supply = args['old_supply']
        # new_supply = args['new_supply']
        # amount = new_supply - old_supply
        # if amount != 0:
        #     current_time = chain.blocks.head.timestamp
        #     dt = datetime.utcfromtimestamp(ts).strftime("%m/%d/%Y, %H:%M:%S")
        #     msg = f'🔒 *veYFI Supply Change Detected!*'
        #     msg += f'\n\n*Supply change*: {round(amount/1e18,2):,} YFI'
        #     msg += f'\n\n🔗 [View on Etherscan](https://etherscan.io/tx/{txn_hash})'
        #     chat_id = CHAT_IDS["WAVEY_ALERTS"]
        #     if alerts_enabled:
        #         chat_id = CHAT_IDS["VEYFI"]
        #     bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

def alert_fee_distributor(last_block, current_block):
    deploy_block = 11_278_886
    DAY = 60 * 60 * 24
    WEEK = DAY * 7
    three_crv = Contract('0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490')
    pool = Contract('0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7')
    ve = Contract('0x5f3b5DfEb7B28CDbD7FAba78963EE202a494e2A2')
    yearn = convert('curve-voter.ychad.eth', AddressType)
    start = max(last_block, deploy_block)
    fee_distributor = Contract('0xA464e6DCda8AC41e03616F95f4BC98a13b8922Dc')
    logs = list(fee_distributor.CheckpointToken.range(start, current_block))
    for l in logs:
        args = l.dict()['event_arguments']
        block = l.block_number
        txn_hash = l.transaction_hash
        time = args['time']
        amount = args['tokens'] / 1e18
        if amount > 0:
            current_time = chain.blocks.head.timestamp
            next_week_start = int(time / WEEK) * WEEK + WEEK
            if next_week_start < time + DAY:
                until = time + DAY
            else:
                until = next_week_start
            dt = datetime.utcfromtimestamp(until).strftime("%m/%d/%Y, %H:%M:%S")
            print(f'{txn_hash} | {amount} | claimable at {dt}')
            amt = round(amount*pool.get_virtual_price()/1e18,2)
            msg = f'⚖️ *New veCRV Fees Detected!*'
            msg += f'\n\n*Total Amount*: ${amt:,}'
            ratio = ve.balanceOfAt(yearn, block) / ve.totalSupply()
            amt = round(amt*ratio,2)
            msg += f'\n\n*Est. Yearn Amount*: ${amt:,}'
            msg += f'\n\n*Claimable At*: {dt}'
            msg += f'\n\n🔗 [View on Etherscan](https://etherscan.io/tx/{txn_hash})'
            chat_id = CHAT_IDS["WAVEY_ALERTS"]
            if alerts_enabled:
                chat_id = CHAT_IDS["CURVE_WARS"]
            bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

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
        if amount == 0:
            continue
        fee = args['fee']
        gauge_name = ''
        abbr, link, briber_markdown = abbreviate_address(briber)
        abbr, link, gauge_markdown = abbreviate_address(gauge)
        try:
            gauge_name = Contract(gauge).name()
        except:
            pass
        amt = round(amount/10**token.decimals(),2)
        fee = round(fee/10**token.decimals(),2)
        msg = f'🤑 *New Bribe Add Detected!*'
        msg += f'\n\n*Amount*: {amt:,} {token.symbol()}'
        msg += f'\n*Gauge*: {gauge_name} {gauge_markdown}'
        msg += f'\n*Briber*: {briber_markdown}'
        msg += f'\n*Fee*: {fee:,} {token.symbol()}'
        msg += f'\n\n🔗 [View on Etherscan](https://etherscan.io/tx/{txn_hash})'
        chat_id = CHAT_IDS["WAVEY_ALERTS"]
        if alerts_enabled:
            chat_id = CHAT_IDS["YBRIBE"]
        bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

    voter = '0xF147b8125d2ef93FB6965Db97D6746952a133934'
    logs = list(ybribe.RewardClaimed.range(start, current_block, search_topics={'user': voter}))
    for l in logs:
        args = l.dict()['event_arguments']
        txn_hash = l.transaction_hash
        user = args['user']
        gauge = args['gauge']
        # token = Contract(args['reward_token'])
        amount = args['amount']

        gauge_name = ''
        abbr, link, markdown = abbreviate_address(user)
        user = markdown
        abbr, link, markdown = abbreviate_address(gauge)
        gauge = markdown
        try:
            gauge_name = Contract(gauge).name()
        except:
            pass
        amt = round(amount/10**18,2)
        msg = f'💰 *Bribe Claim Detected!*'
        msg += f'\n\n*Amount*: {amt:,}'# {token.symbol()}'
        msg += f'\n*Gauge*: {gauge_name} {gauge}'
        msg += f'\n*User*: {user}'
        msg += f'\n\n🔗 [View on Etherscan](https://etherscan.io/tx/{txn_hash})'
        chat_id = CHAT_IDS["WAVEY_ALERTS"]
        if alerts_enabled:
            chat_id = CHAT_IDS["YBRIBE"]
        bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

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
        if value > alert_size_threshold:
            block = l.block_number
            ts = chain.blocks[block].timestamp
            txn_hash = l.transaction_hash
            txn_receipt = networks.provider.get_receipt(txn_hash)
            receiver = txn_receipt.transaction.sender # args['receiver'] <--- this method gets 
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

    slippages = {}
    for trade in trades:
        buy_token_address = trade['buy_token_address']

        # If there is a trade for eth, use weth instead since TH will never
        # get native eth
        if buy_token_address.lower() == "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE".lower():
            buy_token_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

        # we might have calculated the slippage previously
        if buy_token_address in slippages:
            continue

        buy_token = project.ERC20.at(buy_token_address)
        before = buy_token.balanceOf(trade_handler, block_identifier=block-1)
        after = buy_token.balanceOf(trade_handler, block_identifier=block+1)
        slippages[buy_token_address] = after - before

    return slippages


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
            if sell_token == '0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2':
                sell_token_symbol = 'MKR'
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
            if buy_token == '0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2':
                buy_token_symbol = 'MKR'
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

def format_solver_alert(solver, txn_hash, block, trade_data, slippages):
    prod_solver = '0x398890BE7c4FAC5d766E1AEFFde44B2EE99F38EF'
    cow_explorer_url = f'https://explorer.cow.fi/orders/{trade_data[0]["order_uid"]}'
    cow_explorer_url = f'https://explorer.cow.fi/tx/{txn_hash}'
    ethtx_explorer_url = f'https://ethtx.info/mainnet/{txn_hash}'
    tonkers_base_url = f'https://prod.seasolver.dev/route/'
    eigen_url = f'https://eigenphi.io/mev/eigentx/{txn_hash}'
    barn_solver = '0x8a4e90e9AFC809a69D2a3BDBE5fff17A12979609'
    if solver == barn_solver:
        tonkers_base_url = f'https://barn.seasolver.dev/route/'
    txn_receipt = networks.provider.get_receipt(txn_hash)
    ts = chain.blocks[block].timestamp
    index = get_index_in_block(txn_hash)
    index = index if index != 1_000_000 else "???"

    dt = datetime.utcfromtimestamp(ts).strftime("%m/%d %H:%M")
    msg = f'{"🧜‍♂️" if solver == prod_solver else "🐓"} *New solve detected!*\n'
    msg += f'by [{solver[0:7]}...]({etherscan_base_url}address/{solver})  index: {index} @ {dt}\n\n'
    msg += f'📕 *Trade(s)*:\n'
    for t in trade_data:
        user = t["owner"]
        sell_amt = round(t["sell_amount"]/10**t["sell_token_decimals"],4)
        buy_amt = round(t["buy_amount"]/10**t["buy_token_decimals"],4)
        buy_token = t["buy_token_address"]
        if buy_token.lower() == "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE".lower():
            buy_token = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
        msg += f'    [ 🐻‍❄️ ]({tonkers_base_url}{t["sell_token_address"]}/{buy_token}) | [{t["sell_token_symbol"]}]({etherscan_base_url}token/{t["sell_token_address"]}) {sell_amt:,} -> [{t["buy_token_symbol"]}]({etherscan_base_url}token/{t["buy_token_address"]}) {buy_amt:,} | [{user[0:7]}...]({etherscan_base_url}address/{user})\n'
    msg += "\n✂️ *Slippages*"
    for key in slippages:
        token = project.ERC20.at(key)
        slippage = slippages[key]
        color = "🔴" if slippage < 0 else "🟢"
        amount = round(slippage/10**token.decimals(),4)
        try:
            msg += f"\n   {color} {token.symbol()}: {amount}"
        except:
            msg += f"\n   {color} -SymbolError-: {amount}"
    msg += f'\n\n{calc_gas_cost(txn_receipt)}'
    msg += f'\n\n🔗 [Etherscan]({etherscan_base_url}tx/{txn_hash}) | [Cow]({cow_explorer_url}) | [Eigen]({eigen_url}) | [EthTx]({ethtx_explorer_url})'

    # Add slippage info

    if alerts_enabled:
        chat_id = CHAT_IDS["GNOSIS_CHAIN_POC"]
    else:
        chat_id = CHAT_IDS["WAVEY_ALERTS"]
    bot.send_message(chat_id, msg, parse_mode="markdown", disable_web_page_preview = True)

def abbreviate_address(address):
    link = f'https://etherscan.io/address/{address}'
    if address in YFI_LOCKERS:
        abbr = YFI_LOCKERS[address]
        markdown = f'[{abbr}]({link})'
    else:
        abbr = address[0:7]
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

def get_index_in_block(txn_hash):
    tx = chain.provider.get_receipt(txn_hash)
    hashes = [x.txn_hash.hex() for x in chain.blocks[tx.block_number].transactions]
    try:
        return hashes.index(tx.txn_hash)
    except:
        return 1_000_000 # Not found