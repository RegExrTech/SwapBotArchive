import os
from flask import Flask, request, render_template, redirect
import json
import time
from collections import defaultdict
from flask import jsonify
from werkzeug.serving import WSGIRequestHandler, _log
import traceback
import sys

#https://stackoverflow.com/questions/54141751/how-to-disable-flask-app-run-s-default-message
cli = sys.modules['flask.cli']
cli.show_server_banner = lambda *x: None

app = Flask(__name__)

class JsonHelper:
	def get_db(self, fname, encode_ascii=True):
		with open(fname) as json_data:
			data = json.load(json_data)
		return data

	def dump(self, db, fname):
		with open(fname, 'w') as outfile:
			outfile.write(json.dumps(db, sort_keys=True, indent=4))

json_helper = JsonHelper()

swaps_fname = 'database/{sub_name}-swaps.json'
comment_fname = 'database/comments.json'
username_lookup_fname = 'Discord/paired_usernames.json'
pending_requests_fname = "Discord/pending_requests.json"

swap_data = {}
comment_data = {}
username_lookup = {}
pending_requests = {}

def get_alias(user_id, current_platform, desired_platform):
	if current_platform not in username_lookup:
		return
	if desired_platform not in username_lookup:
		return
	if user_id not in username_lookup[current_platform]:
		return
	return username_lookup[current_platform][user_id]

def get_user_summary(sub_data, author, current_platform):
	"""Returns transaction entries.
		Example: {
			'reddit': {
				'legacy_count': 12,
				'transactions': [
					{
						'post_id': 'abc',
						'comment_id': 'abc',
						'timestamp': 'abc',
						'partner': 'abc'
					}
				]
			}
		}
	"""
	summary = {}
	usernames_on_platforms = username_lookup[current_platform]
	for platform in sub_data:
		if author in usernames_on_platforms:
			platforms_to_username = usernames_on_platforms[author]
			if platform in platforms_to_username:
				platform_author_name = platforms_to_username[platform]
				if platform_author_name in sub_data[platform]:
					summary[platform] = sub_data[platform][platform_author_name]
		if platform == current_platform:
			if author in sub_data[platform]:
				summary[platform] = sub_data[platform][author]
	return summary

@app.route('/add-comment/', methods=['POST'])
def add_comment():
	"""
	Given a comment ID and sub name, manually adds it to the
	list of comments to check.

	Requested Form Params:
	String sub_name: The name of the current subreddit
	String comment_id: The ID of the comment where the trade took place
	String platform: The platform the comment is coming from

	return JSON {}
	"""

	sub_name = request.form["sub_name"]
	comment_id = request.form["comment_id"]
	platform = request.form["platform"]

	global comment_data

	if sub_name not in comment_data:
		comment_data[sub_name] = {platform: {'active': [], 'archived': []}}
	if platform not in comment_data[sub_name]:
		comment_data[sub_name][platform] = {'active': [], 'archived': []}

	if comment_id not in comment_data[sub_name][platform]['active'] and comment_id not in comment_data[sub_name][platform]['archived']:
		comment_data[sub_name][platform]['active'].append(comment_id)
	json_helper.dump(comment_data, comment_fname)
	return jsonify({})


@app.route('/get-comments/', methods=['POST'])
def get_comments():
	"""
	Given a list of new IDs, returns a list of unique IDs to check and a list of unique IDs which are new to the system

	Requested Form Params:
	String sub_name: The name of the current subreddit
	String active: Denotes either active or archived ('True' or 'False')
	List(String) ids: List of strings of ids to include with active comments
	String platform: The platform to get comments from

	Return JSON {'ids': List(String), 'new_ids': List(String)}
	"""
	new_ids = []
	sub_name = request.form["sub_name"]
	active = request.form['active'] == 'True'
	ids = request.form['ids'].split(",")
	platform = request.form["platform"]

	if not ids[0]:
		ids = []

	global comment_data
	if sub_name not in comment_data:
		comment_data[sub_name] = {platform: {'active': [], 'archived': []}}
	if platform not in comment_data[sub_name]:
		comment_data[sub_name][platform] = {'active': [], 'archived': []}

	if active:
		prev_ids = comment_data[sub_name][platform]['active']
	else:
		prev_ids = comment_data[sub_name][platform]['archived']

	for id in ids:
		if id not in prev_ids:
			prev_ids.append(id)
			new_ids.append(id)
	json_helper.dump(comment_data, comment_fname)
	return jsonify({'ids': list(set(prev_ids)), 'new_ids': list(set(new_ids))})

@app.route('/check-comment/', methods=['POST'])
def check_comment():
	"""
	Updates the database for a confirmed trade if it is not a duplicate

	Requested Form Params:
	String sub_name: The name of the current subreddit
	String author1: The first trade partner's name
	String author2: The second trade partner's name
	String post_id: The ID of the post where the trade took place
	Optional(String) top_level_comment_id: The ID of the top most comment in the comment chain (usually indicates automod thread)
	String comment_id: The ID of the comment where the trade took place
	String platform: The platform the comment is coming from

	Return JSON {username1: is_dupliate (string representation of boolean), username2: ...}
	"""

	global swap_data
	global comment_data
	sub_name = request.form["sub_name"]
	platform = request.form["platform"].lower()
	if sub_name not in swap_data:
		swap_data[sub_name] = {platform: {}}
	if platform not in swap_data[sub_name]:
		swap_data[sub_name][platform] = {}

	sub_data = swap_data[sub_name][platform]

	author1 = request.form['author1']
	author2 = request.form['author2']
	return_data = {author1: {'is_duplicate': 'False'}, author2: {'is_duplicate': 'False'}}
	post_id = request.form['post_id']
	comment_id = request.form['comment_id']
	if 'top_level_comment_id' in request.form:
		top_level_comment_id = request.form['top_level_comment_id']
	else:
		top_level_comment_id = ""

	if author1 not in sub_data:
		sub_data[author1] = {'transactions': []}
	if author2 not in sub_data:
		sub_data[author2] = {'transactions': []}

	if top_level_comment_id:
		if any([x['partner'] == author2 and x['post_id'] == post_id and x['comment_id'] == top_level_comment_id for x in sub_data[author1]['transactions']]):
			return_data[author1]['is_duplicate'] = 'True'
		else:
			sub_data[author1]['transactions'].append({'partner': author2, 'post_id': post_id, 'comment_id': top_level_comment_id, 'timestamp': int(time.time())})
	else:
		if platform == 'discord':
			if any([x['partner'] == author2 and x['comment_id'] == comment_id for x in sub_data[author1]['transactions']]):
				return_data[author1]['is_duplicate'] = 'True'
			else:
				sub_data[author1]['transactions'].append({'partner': author2, 'post_id': post_id, 'comment_id': comment_id, 'timestamp': int(time.time())})
		else:
			if any([x['partner'] == author2 and x['post_id'] == post_id for x in sub_data[author1]['transactions']]):
				return_data[author1]['is_duplicate'] = 'True'
			else:
				sub_data[author1]['transactions'].append({'partner': author2, 'post_id': post_id, 'comment_id': comment_id, 'timestamp': int(time.time())})

	if top_level_comment_id:
		if any([x['partner'] == author1 and x['post_id'] == post_id and x['comment_id'] == top_level_comment_id for x in sub_data[author2]['transactions']]):
			return_data[author2]['is_duplicate'] = 'True'
		else:
			sub_data[author2]['transactions'].append({'partner': author1, 'post_id': post_id, 'comment_id': top_level_comment_id, 'timestamp': int(time.time())})
	else:
		if platform == 'discord':
			if any([x['partner'] == author1 and x['comment_id'] == comment_id for x in sub_data[author2]['transactions']]):
				return_data[author2]['is_duplicate'] = 'True'
			else:
				sub_data[author2]['transactions'].append({'partner': author1, 'post_id': post_id, 'comment_id': comment_id, 'timestamp': int(time.time())})
		else:
			if any([x['partner'] == author1 and x['post_id'] == post_id for x in sub_data[author2]['transactions']]):
				return_data[author2]['is_duplicate'] = 'True'
			else:
				sub_data[author2]['transactions'].append({'partner': author1, 'post_id': post_id, 'comment_id': comment_id, 'timestamp': int(time.time())})

	if sub_name not in comment_data:
		comment_data[sub_name] = {}
	if platform not in comment_data[sub_name]:
		comment_data[sub_name][platform] = {}
	if 'active' not in comment_data[sub_name][platform]:
		comment_data[sub_name][platform]['active'] = []
	if 'archived' not in comment_data[sub_name][platform]:
		comment_data[sub_name][platform]['archived'] = []
	if comment_id in comment_data[sub_name][platform]['active']:
		comment_data[sub_name][platform]['active'].remove(comment_id)
	if comment_id in comment_data[sub_name][platform]['archived']:
		comment_data[sub_name][platform]['archived'].remove(comment_id)
	json_helper.dump(swap_data[sub_name], swaps_fname.format(sub_name=sub_name))
	json_helper.dump(comment_data, comment_fname)
	return jsonify(return_data)

@app.route('/get-summary/', methods=['POST'])
def get_summary():
	"""
	Given a sub and a username, get their list of confirmed trades

	Requested Form Params:
	String sub_name: The name of the current subreddit
	String username: The name of the user to check feedback for
	String current_platform: The name of the platform making the request

	Return JSON {'data': List(Transactions)}
	"""

	sub_name = request.form["sub_name"]
	current_platform = request.form["current_platform"]
	if sub_name not in swap_data:
		return jsonify({'data': []})
	sub_data = swap_data[sub_name]
	username = request.form['username']
	data = get_user_summary(swap_data[sub_name], username, current_platform)
	return jsonify({'data': data})

@app.route('/get-summary-from-subs/', methods=['POST'])
def get_summary_from_subs():
	"""
	Like get_summary(), but for multiple subs

	Requested Form Params:
	List[String] sub_names: Comma-seperated list of sub names to check
	String username: The name of the user to check feedback for
	String current_platform: The name of the platform making the request

	Return JSON {'data': {'sub_name': {'platform': {Optional('legacy_count'): int, 'transactions': [{partner, post_id, comment_id, timestamp}]}}}}
	"""

	current_platform = request.form["current_platform"]
	username = request.form['username']
	sub_names = request.form["sub_names"].split(",")
	data = {}
	for sub_name in sub_names:
		if sub_name not in swap_data:
			continue
		data[sub_name] = get_user_summary(swap_data[sub_name], username, current_platform)
	return jsonify({'data': data})

@app.route('/archive-comment/', methods=['POST'])
def archive_comment():
	"""
	Removes a comment from the active list and moves it ot the archive list

	Requested Form Parms:
	String sub_name: The name of the current subreddit
	String comment_id: The ID of the comment to archive
	String platform: The platform the comment is coming from

	Return JSON {}
	"""

	global comment_data
	sub_name = request.form["sub_name"]
	platform = request.form["platform"]
	comment_id = request.form['comment_id']
	if comment_id in comment_data[sub_name][platform]['active']:
		comment_data[sub_name][platform]['active'].remove(comment_id)
	comment_data[sub_name][platform]['archived'].append(comment_id)
	json_helper.dump(comment_data, comment_fname)
	return jsonify({})

@app.route('/remove-comment/', methods=['POST'])
def remove_comment():
	"""
	Removes a comment from being tracked

	Requested Form Params:
	String sub_name: The name of the current subreddit
	String comment_id: The ID of the comment to remove
	String platform: The platform the comment is coming from

	Return JSON {}
	"""

	global comment_data
	sub_name = request.form["sub_name"]
	platform = request.form["platform"]
	comment_id = request.form['comment_id']
	while comment_id in comment_data[sub_name][platform]['active']:
		comment_data[sub_name][platform]['active'].remove(comment_id)
	while comment_id in comment_data[sub_name][platform]['archived']:
		comment_data[sub_name][platform]['archived'].remove(comment_id)
	json_helper.dump(comment_data, comment_fname)
	return jsonify({})

@app.route('/add-batch-swap/', methods=['POST'])
def add_batch_swap():
	"""
	Adds multiple swaps at once for multiple users

	Requested Form Params:
	String sub_name: The name of the current subreddit
	String platform: The platform the swaps are coming from
	Dict user_data {username: swap_text}:
		String username: Username for a reddit user to update
		List[Dict] transaction_data {post_id, comment_id, partner, timestamp}

	Return JSON {username1: String(Boolean representation of if the user was updated or not), username2: ...}
	"""

	global swap_data
	return_data = {}
	sub_name = request.get_json()["sub_name"]
	platform = request.get_json()["platform"]
	if sub_name not in swap_data:
		swap_data[sub_name] = {platform: {}}
	if platform not in swap_data[sub_name]:
		swap_data[sub_name][platform] = {}
	user_data = request.get_json()["user_data"]
	for username in user_data:
		username = username.lower()
		return_data[username] = 'False'
		if username not in swap_data[sub_name][platform]:
			swap_data[sub_name][platform][username] = {'transactions': []}
		for transaction_data in user_data[username]:
			if transaction_data['post_id'] == "LEGACY TRADE":
				if 'legacy_count' not in swap_data[sub_name][platform][username]:
					swap_data[sub_name][platform][username]['legacy_count'] = 0
				swap_data[sub_name][platform][username]['legacy_count'] += 1
				return_data[username] = 'True'
			else:
				if any([x['post_id'] == transaction_data['post_id'] and x['partner'] == transaction_data['partner'] for x in swap_data[sub_name][platform][username]['transactions']]):
					continue
				swap_data[sub_name][platform][username]['transactions'].append({'post_id': transaction_data['post_id'], 'comment_id': transaction_data['comment_id'], 'partner': transaction_data['partner'], 'timestamp': transaction_data['timestamp']})
				return_data[username] = 'True'
	json_helper.dump(swap_data[sub_name], swaps_fname.format(sub_name=sub_name))
	return jsonify(return_data)


@app.route('/remove-swap/', methods=['POST'])
def remove_swap():
	"""
	Removes swaps from a user's profile.

	Requested Form Params:
	String sub_name: The name of the current subreddit
	String username: The name of the user to add swaps for
	String platform: The platform the swaps are being removed from
	Dict transaction_data {username: swap_text}:
		String username: Username for a reddit user to update
		List[Dict] transaction_data {post_id, comment_id, partner, timestamp}


	Return JSON {}
	"""

	global swap_data
	sub_name = request.get_json()["sub_name"]
	platform = request.get_json()["platform"]
	username = request.get_json()["username"]
	transaction_data = request.get_json()["transaction_data"]
	if sub_name not in swap_data:
		return jsonify({})
	if platform not in swap_data[sub_name]:
		return jsonify({})
	if username not in swap_data[sub_name][platform]:
		return jsonify({})
	for transaction in transaction_data:
		if transaction['post_id'] == "LEGACY TRADE" and 'legacy_count' in swap_data[sub_name][platform][username] and swap_data[sub_name][platform][username]['legacy_count'] > 0:
			swap_data[sub_name][platform][username]['legacy_count'] -= 1
		else:
			swap_data[sub_name][platform][username]['transactions'] = [x for x in swap_data[sub_name][platform][username]['transactions'] if not (x['post_id'] == transaction['post_id'] and x['comment_id'] == transaction['comment_id'] and x['partner'] == transaction['partner'])]
	json_helper.dump(swap_data[sub_name], swaps_fname.format(sub_name=sub_name))
	return jsonify({})

@app.route('/remove-user/', methods=["POST"])
def remove_user():
	"""
	Removes a user and all of their feedback from a given sub

	Requested Form Params:
	String sub_name: The name of the current subreddit
	String platform: The platform from which to remove the user
	String username: The name of the user to remove

	Return JSON {status: string}
	"""

	global swap_data
	sub_name = request.form["sub_name"]
	username = request.form['username']
	platform = request.form['platform']
	if sub_name not in swap_data:
		return jsonify({'status': sub_name + ' not found'})
	if platform not in swap_data[sub_name]:
		return jsonify({'status': sub_name + ' - ' + platform + ' not found'})
	if username in swap_data[sub_name][platform]:
		del swap_data[sub_name][platform][username]
	else:
		return jsonify({'status': username + ' not found'})
	json_helper.dump(swap_data[sub_name], swaps_fname.format(sub_name=sub_name))
	return jsonify({'status': username + " removed from " + sub_name + " on " + platform})

@app.route('/get-user-count-from-subs/', methods=["GET"])
def get_user_count_from_subs():
	"""Gets flair count for a given user from given subs

	Requested Form Params:
	List(String) sub_names: comma seperated list of sub_names
	String current_platform: The current platform the username name is tied to
	String author: username in question

	Return JSON {count: int}
	"""

	author = request.form["author"]
	current_platform = request.form["current_platform"]
	sub_names = request.form["sub_names"].split(",")
	count = 0
	for sub_name in sub_names:
		if sub_name not in swap_data:
			continue
		data = get_user_summary(swap_data[sub_name], author, current_platform)
		for platform in data:
			if 'legacy_count' in data[platform]:
				count += data[platform]['legacy_count']
			count += len(data[platform]['transactions'])
	return jsonify({'count': count})

@app.route('/get-paired-usernames/', methods=["GET"])
def get_paired_usernames():
	"""Returns the current paired username lookup table

	Return JSON username_lookup
	"""
	return jsonify(username_lookup)

@app.route('/add-username-pairing/', methods=["POST"])
def add_username_pairing():
	"""Updates the paired username lookup table

	Requested Form Params:
	String platform1: The first platform for pairing
	String platform2: The second platform for pairing
	String username1: The corresponding first username for pairing
	String username2: The corresonding second username for pairing

	Return JSON {}
	"""
	global username_lookup
	platform1 = request.form["platform1"]
	platform2 = request.form["platform2"]
	username1 = request.form["username1"]
	username2 = request.form["username2"]

	if platform1 not in username_lookup:
		username_lookup[platform1] = {}
	if username1 not in username_lookup[platform1]:
		username_lookup[platform1][username1] = {platform2: username2}
	if platform2 not in username_lookup:
		username_lookup[platform2] = {}
	if username2 not in username_lookup[platform2]:
		username_lookup[platform2][username2] = {platform1: username1}

	json_helper.dump(username_lookup, username_lookup_fname)
	return jsonify({})

@app.route('/remove-username-pairing/', methods=["POST"])
def remove_username_pairing():
	"""Removes a paired selection of usernames

	Requested Form Params:
	String platform1: The first platform for pairing
	String platform2: The second platform for pairing
	String username1: The corresponding first username for pairing
	String username2: The corresonding second username for pairing

	Return JSON {'platform': 'removed_username', ...}
	"""
	global username_lookup
	platform1 = request.form["platform1"]
	platform2 = request.form["platform2"]
	username1 = request.form["username1"]
	username2 = request.form["username2"]

	removed = {}
	if platform1 in username_lookup and username1 in username_lookup[platform1]:
		del(username_lookup[platform1][username1])
		removed[platform1] = username1
	if platform2 in username_lookup and username2 in username_lookup[platform2]:
		del(username_lookup[platform2][username2])
		removed[platform2] = username2

	json_helper.dump(username_lookup, username_lookup_fname)
	return jsonify(removed)

@app.route('/get-pending-account-pairing-requests/', methods=["GET"])
def get_pending_account_pairing_requests():
	"""Returns the current mapping of account pairing requests

	Return JSON pending_requests
	"""
	return jsonify(pending_requests)

@app.route('/add-account-pairing-request/', methods=["POST"])
def add_account_pairing_request():
	"""Updates the pending_requests mapping. This is only for discord->reddit

	Requested Form Params:
	String discord_user_id
	String reddit_username
	float request_timestamp
	String reddit_message_id
	String discord_message_id

	Return JSON {}
	"""
	global pending_requests
	discord_user_id = request.form["discord_user_id"]
	reddit_username = request.form["reddit_username"]
	request_timestamp = request.form["request_timestamp"]
	reddit_message_id = request.form["reddit_message_id"]
	discord_message_id = request.form["discord_message_id"]

	pending_requests[discord_user_id] = {"reddit_username": reddit_username, "request_timestamp": time.time(), 'reddit_message_id': reddit_message_id, 'discord_message_id': discord_message_id}

	json_helper.dump(pending_requests, pending_requests_fname)
	return jsonify({})

@app.route('/remove-account-pairing-request/', methods=["POST"])
def remove_account_pairing_request():
	"""Removes a paired selection of usernames

	Requested Form Params:
	String discord_user_id

	Return JSON {}
	"""
	global pending_requests
	discord_user_id = request.form["discord_user_id"]

	if discord_user_id not in pending_requests:
		return jsonify({'error': 'id ' + discord_user_id + ' not found in pending requests.'})
	del(pending_requests[discord_user_id])
	json_helper.dump(pending_requests, pending_requests_fname)
	return jsonify({})


@app.route('/dump/', methods=["POST"])
def dump():
	for sub_name in swap_data:
		json_helper.dump(swap_data[sub_name], swaps_fname.format(sub_name=sub_name))
	json_helper.dump(comment_data, comment_fname)
	json_helper.dump(username_lookup, username_lookup_fname)
	json_helper.dump(pending_requests, pending_requests_fname)
	return jsonify({})

@app.route('/get-db/', methods=["GET"])
def get_db():
	return jsonify(swap_data)

class MyRequestHandler(WSGIRequestHandler):
	# Just like WSGIRequestHandler, but without "code"
	def log_request(self, code='-', size='-'):
		if 200 == code:
			pass
		elif 'Address already in use' in self.requestline:
			pass
		else:
			self.log('info', '"%s" %s %s', self.requestline, code, size)

def port_in_use(port):
	import socket
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
		return s.connect_ex(('0.0.0.0', port)) == 0

@app.before_first_request
def launch():
	global swap_data
	global comment_data
	global username_lookup
	global pending_requests
	for fname in os.listdir('database'):
		if '-swaps.json' in fname:
			try:
				_db = json_helper.get_db('database/'+fname)
			except Exception as e:
				print("Unable to load database for " + fname + " with error " + str(e))
				raise e
			swap_data[fname.split("-")[0]] = _db
	comment_data = json_helper.get_db(comment_fname)
	username_lookup = json_helper.get_db(username_lookup_fname, False)
	pending_requests = json_helper.get_db(pending_requests_fname)

if __name__ == "__main__":
	port = 8000
	try:
		if not port_in_use(port):
			app.run(host= '0.0.0.0', port=port, request_handler=MyRequestHandler)
	except Exception as e:
		if 'Address already in use'.lower() not in str(e).lower():
			print(e)
			print(traceback.format_exc())
