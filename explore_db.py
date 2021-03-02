
from collections import defaultdict
import json

FNAME = 'database/swaps.json'
#FNAME = 'database/comments.json'

# required function for getting ASCII from json load
def ascii_encode_dict(data):
        ascii_encode = lambda x: x.encode('ascii') if isinstance(x, unicode) else x
        return dict(map(ascii_encode, pair) for pair in data.items())

# Function to load the DB into memory
def get_db(database_file_name=FNAME):
        with open(database_file_name) as json_data: # open the funko-shop's data
                funko_store_data = json.load(json_data, object_hook=ascii_encode_dict)
        return funko_store_data

def dump(swap_data, database_file_name=FNAME):
        with open(database_file_name, 'w') as outfile:  # Write out new data
                outfile.write(str(json.dumps(swap_data))
                        .replace("'", '"')
                        .replace(', u"', ', "')
                        .replace('[u"', '["')
                        .replace('{u"', '{"')
                        .encode('ascii','ignore'))

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
		if sub in ['digitalcodesell', 'uvtrade']:
			continue
		for user in db[sub]:
			all_users[user] = ''
			for sub2 in db:
				if sub2 in ['digitalcodesell', 'uvtrade']:
					continue
				if sub2 == sub:
					continue
				if user in db[sub2]:
					users.append(user)
	users = list(set(users))

	for user in users:
		print("=== " + user + " ===")
		for sub in db:
			if sub in ['digitalcodesell', 'uvtrade']:
				continue
			if user in db[sub]:
				print("  " + sub + " - " + str(len(db[sub][user])))
	print("Total cross-sub users: " + str(len(users)))
	print("Total Users: " + str(len(all_users.keys())))

def get_highest(db):
	for sub in db:
		highest = 0
		h_user = ""
		for user in db[sub]:
			if len(db[sub][user]) > highest and not user == 'none':
				highest = len(db[sub][user])
				h_user = user
		print(sub + " - " + h_user + " - " + str(highest))

def print_user_in_sub(db, sub, user):
	print("=== " + sub + " - " + user + " ===")
	print("    " + "\n    ".join(db[sub][user]))

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

db = get_db()

#get_common_users(db)
#get_highest(db)

for user in ["HerbyVershmales".lower()]:
	user = user.lower()
	for sub in db:
#		print(sub + " - " + str(len(db[sub])) + " users")
		if user in db[sub]:
			print(user + " - " + sub + "\n  * " + "\n  * ".join(db[sub][user]) + "\n\n")

#dump(db)
