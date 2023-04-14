# import json, os, time
# from dotenv import load_dotenv, find_dotenv
# from dataclasses import dataclass
# from decimal import Decimal
# from functools import cached_property
# from typing import List, Optional, Union
# from ape import Contract, chain, project, networks, convert
# from ape.api import ReceiptAPI
# from ape.types import AddressType, ContractLog
# from ape.utils import ManagerAccessMixin
# from eth_abi.packed import encode_abi_packed
# from eth_utils import keccak, humanize_seconds
# from datetime import datetime, timezone
# from sqlalchemy import desc, asc
# from models import Reports, Event, Transactions, Session, engine, select

from ape import Contract, chain
from eth_utils import humanize_seconds
from datetime import datetime

def main():
    current_block = chain.blocks.height
    # Get a list of all veYFI lockers
    deploy_block = 15_974_608
    veyfi = Contract('0x90c1f9220d90d3966FbeE24045EDd73E1d588aD5')
    logs = list(veyfi.ModifyLock.range(deploy_block, current_block))
    users = []
    for l in logs:
        args = l.dict()['event_arguments']
        user = args['user']
        if user not in users:
            users.append(user)

    # Now let's print each locker's position
    helper = Contract('0x5A70cD937bA3Daec8188E937E243fFa43d6ECbe8')
    for u in users:
        data = helper.getPositionDetails(u)
        print(f"\nUSER: {u}")
        items = enumerate(data.items())
        for idx, i in items:
            if idx < 4:
                print(i[0],int(i[1])/1e18)
            elif idx == 4:
                # Unlock time
                if i[1] == 0:
                    print(i[0], 0)
                else:
                    d = datetime.utcfromtimestamp(i[1]).strftime('%Y-%m-%d %H:%M:%S')
                    print(i[0], d)
            elif idx == 5:
                # Time until
                if i[1] == 0:
                    d = 0
                else:
                    print(i[0], humanize_seconds(i[1]))

#         block = l.block_number
#         ts = chain.blocks[block].timestamp
#         txn_hash = l.transaction_hash
#         txn_receipt = networks.provider.get_receipt(txn_hash)
#         idx = 0
#         args = s.dict()['event_arguments']
#         old_supply = args['old_supply']
#         new_supply = args['new_supply']
#         # code.interact(local=locals())
#         try:
#             user = list(modify_logs)[idx]['user']
#         except:
#             continue
#         amount = new_supply - old_supply

#     with Session(engine) as session:
#         query = select(Reports).where(
#             Reports.chain_id == chain.chain_id and Reports.block > current_block - 100_000
#         ).order_by(desc(Reports.block))
#         previous_report = session.exec(query).first()
#         print(previous_report)
#         print(current_block,current_block - 100_000, chain.chain_id)
#         assert False

# load_dotenv(find_dotenv())

# from ape import chain, networks, Contract
# import pandas as pd
# import altair as alt
# import requests
# from eth_utils import encode_hex

# def main():
#     networks.parse_network_choice('ethereum:mainnet:https://erigon:FcqDXWV3TEwS2-r3@erigon.yearn.vision').__enter__()

#     alt.data_transformers.disable_max_rows()

#     euler = Contract('0xceD32E95C971610AdF264EC8f619fCBf242D64D7')

#     blocks = list(range(16591488, 16720000, 100))
#     len(blocks)

#     for block in range(16591488, 16720000, 100):
#         euler.underlyingBalanceStored(arg, block_identifier=block)

#     def query_method(method, blocks, *args):
#         tx = method.as_transaction(*args).dict()
#         tx['data'] = encode_hex(tx['data'])

#         for key in ['chainId', 'gas', 'value', 'type', 'maxFeePerGas', 'maxPriorityFeePerGas', 'accessList']:
#             tx.pop(key, None)
#         batch = [
#             {'jsonprc': '2.0', 'id': block, 'method': 'eth_call', 'params': [tx, hex(block)]}
#             for block in blocks
#         ]
#         response = requests.post(chain.provider.uri, json=batch).json()
#         return {block: int(x['result'], 16) / 1e18 for block, x in zip(blocks, response)}


#     data = {
#         'underlyingBalanceStored': query_method(euler.underlyingBalanceStored, blocks)
#     }

#     df = pd.DataFrame(data)
#     df = df.reset_index().rename(columns={'index': 'block'}).melt(id_vars=['block'])
#     df

#     chart = (
#         alt.Chart(df[df.variable.isin(['underlyingBalanceStored'])], title=euler.address)
#         .mark_line()
#         .encode(
#             x=alt.X('block', axis=alt.Axis(labelFlush=False)),
#             y=alt.Y('value', scale=alt.Scale(zero=False)),
#             color='variable'
#         )
#     )
#     chart.save('euler.svg')