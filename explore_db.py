import requests
from collections import defaultdict
import json
import server
import os
import sys
sys.path.insert(0, ".")
import swap
from server import JsonHelper

j = JsonHelper()

FNAME = 'database/comments.json'

def print_sorted_dict(d):
	sorted_d = defaultdict(lambda: [])
	for key in d:
		value = d[key]
		sorted_d[value].append(key)
	keys = sorted_d.keys()
	keys.sort()
	for key in keys:
		for value in sorted_d[key]:
			print(str(key) + " - " + str(value))

def get_common_users(db):
	all_users = {}
	users = []
	for sub in db:
		for user in db[sub]:
			all_users[user] = ''
			for sub2 in db:
				if sub2 == sub:
					continue
				if user in db[sub2]:
					users.append(user)
	users = list(set(users))

	for user in users:
		print("=== " + user + " ===")
		for sub in db:
			if user in db[sub]:
				print("  " + sub + " - " + str(len(db[sub][user])))
	print("Total cross-sub users: " + str(len(users)))
	print("Total Users: " + str(len(all_users.keys())))

def get_highest(db):
	for sub in db:
		for platform in db[sub]:
			highest = 0
			h_user = ""
			for user in db[sub][platform]:
				if len(db[sub][platform][user]) > highest and not user == 'none':
					highest = len(db[sub][platform][user])
					h_user = user
			print(sub + " - " + h_user + " - " + str(highest))

def print_user_in_all_subs(db, user):
	username_lookup = server.json_helper.get_db(server.username_lookup_fname, False)
	usernames = [user]
	for platform in username_lookup:
		if user in username_lookup[platform]:
			usernames += username_lookup[platform][user].values()
	for sub in db:
		for platform in db[sub]:
			for user in usernames:
				if user in db[sub][platform]:
					print_user_in_sub(db, sub, platform, user)

def print_user_in_sub(db, sub, platform, user):
	count = 0
	if 'legacy_count' in db[sub][platform][user]:
		count += db[sub][platform][user]['legacy_count']
	count += len(db[sub][platform][user]['transactions'])
	print("=== " + sub + " - " + platform + " - " + user + " - " + str(count) + " ===")
	if 'legacy_count' in db[sub][platform][user]:
		print("    Legacy Count: " + str(db[sub][platform][user]['legacy_count']))
	print("    " + "\n    ".join([str(x) for x in db[sub][platform][user]['transactions']]))

def count_partners(db, sub, user):
	d = defaultdict(lambda:0)
	for trade in db[sub][user]:
		partner = trade.split(" - ")[0]
		d[partner] += 1
	return d

def get_total_count(db, user):
	total = 0
	for sub in db:
		if user in db[sub]:
			count = len(db[sub][user])
#			print(sub + " - " + str(count))
			total += count
	return total

def check_if_banned(usernames, sub):
	banned = set([])
	for ban in sub.banned(limit=None):
		banned_user = str(ban).lower()
		banned.add(banned_user)
#	print(banned)
#	print(usernames)
	for username in usernames:
		if str(username) in banned:
			print(username)


request_url = "http://0.0.0.0:8000"
db = requests.get(request_url+"/get-db/").json()

for user in [x.lower().split("/")[1] if "/" in x else x.lower() for x in ['BetterInsideTheBox']]:
	print_user_in_all_subs(db, user.lower())

#dump(db)

