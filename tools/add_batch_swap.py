import sys
sys.path.insert(0, '.')
from server import JsonHelper
import requests
import argparse
import swap

parser = argparse.ArgumentParser()
parser.add_argument('sub_name', metavar='C', type=str)
parser.add_argument('platform', metavar='C', type=str)
parser.add_argument('username', metavar='C', type=str)
parser.add_argument('swap_count', metavar='C', type=int)
args = parser.parse_args()
request_url = "http://0.0.0.0:8000"
json_helper = JsonHelper()
requests.post(request_url + "/add-batch-swap/", json={'sub_name': args.sub_name.lower(), 'platform': args.platform.lower(), 'user_data': {args.username.lower(): ",".join(["LEGACY TRADE" for i in range(args.swap_count)])}})
sub_config, reddit, sub = swap.create_reddit_and_sub(args.sub_name.lower())
swap_count = swap.get_swap_count(args.username.lower(), sub_config.gets_flair_from+[sub_config.database_name], args.platform.lower())
swap.update_single_user_flair(sub, sub_config, args.username.lower(), swap_count, [], 0)
