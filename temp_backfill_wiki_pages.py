import requests
import traceback
import time
import os
import sys
sys.path.insert(0, '.')
import Config
import wiki_helper
import swap

sys.path.insert(0, 'logger')
import logger

import argparse

request_url = "http://0.0.0.0:8000"

def main(subname, overview_only):
	skipped_users = []
	sub_config = Config.Config(subname.split(".")[0])
	if not sub_config.bot_username or sub_config.disabled:
		return
	db = requests.get(request_url+"/get-sub-db/", data={'sub': sub_config.subreddit_name}).json()
	if 'reddit' not in db:
		return
	count = 0
	total = len(list(db['reddit'].keys()))
	logger.log("Starting to backfill " + str(total) + " wiki pages for r/" + sub_config.subreddit_name)
	for user in db['reddit'].keys():
		count += 1
		if subname == 'vinylcollectors' and count > 2000 and count < 13000:
			continue
		content = swap.format_swap_count_summary(sub_config, user, 200000)
		overview_content = swap.format_swap_count_overview_summary(content, sub_config, user)
		if overview_only:
			content = ""
		try:
			wiki_helper.update_confirmation_page(user, content, overview_content, sub_config)
		except:
			time.sleep(5)
			try:
				wiki_helper.update_confirmation_page(user, content, overview_content, sub_config)
			except Exception as e:
				logger.log("Failed to make wiki page for u/" + user + " on r/" + sub_config.subreddit_name, e)
				skipped_users.append(user)
				time.sleep(5)
		time.sleep(1)
		if not count % 1000:
			logger.log("Finished user " + str(count) + " out of " + str(total))
	logger.log("Finished backfilling wiki pages for r/" + sub_config.subreddit_name)
	logger.log("Skipped the following users: " + str(skipped_users))

try:
	subnames = [x.split(".")[0] for x in os.listdir("config/")]
	subnames.sort()
	for subname in subnames[::-1]:
		overview_only = False
		if subname in ['watchexchangecanada', 'ygomarketplace', 'watchexchange', 'vinylcollectors', 'sanpedrocactusforsale', 'snackexchange', 'thinkpadsforsale', 'ulgeartrade', 'uvtrade', 'synths4sale']:
			continue
		if subname in ['watchexchangecanada', 'ygomarketplace', 'watchexchange', 'vinylcollectors', 'sanpedrocactusforsale', 'snackexchange', 'thinkpadsforsale', 'ulgeartrade', 'uvtrade', 'synths4sale', 'steelbookswap']:
			overview_only = True
		main(subname, overview_only=overview_only)
except Exception as e:
	logger.log("Uncaught exception when running wiki page backfiller, entire program crashed.", e, traceback.format_exc())
