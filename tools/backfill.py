import json
import praw
import sys
sys.path.insert(0, '.')
import config
import swap

from collections import defaultdict
import time
import re
import requests

request_url = "http://0.0.0.0:8000"

PLATFORM = "reddit"

feedback_sub_name = "WatchExchangeFeedback".lower()
sub_name = "WatchExchange".lower()
feedback_sub_name = "gcxrep"
sub_name = "giftcardexchange"
#feedback_sub_name = "c4crep"
#sub_name = "cash4cash"
#feedback_sub_name = "snackexchange"
#sub_name = "snackexchange"
#feedback_sub_name = "ygomarketplace"
#sub_name = "ygomarketplace"
#feedback_sub_name = "thinkpadsforsale"
#sub_name = "thinkpadsforsale"
#feedback_sub_name = "knife_swap"
#sub_name = "knife_swap"
#feedback_sub_name = "pkmntcgtrades"
#sub_name = "pkmntcgtrades"


# required function for getting ASCII from json load
def ascii_encode_dict(data):
        ascii_encode = lambda x: x.encode('ascii') if isinstance(x, unicode) else x
        return dict(map(ascii_encode, pair) for pair in data.items())

# Function to load the DB into memory
def get_db(database_file_name):
        with open(database_file_name) as json_data: # open the funko-shop's data
                funko_store_data = json.load(json_data, object_hook=ascii_encode_dict)
        return funko_store_data

def temp(sub, db):
	to_return = []
	for flair in sub.flair():
		username = str(flair['user']).lower()
		if username == 'none':
			continue
		if username == "automoderator":
			continue
		flair_text = flair['flair_text']
		if not flair_text or  "|" not in flair_text or username not in db:
			to_return.append(username)
			print(username + " - " + str(flair_text))
	return to_return

def GetUserToCss(sub):
	db = get_db("database/swaps.json")[sub_name][PLATFORM]
	count = 0
	d = defaultdict(lambda: [])
	# {u'flair_css_class': u'i-buy', u'user': Redditor(name='Craig'), u'flair_text': u'Buyer'}
	for flair in sub.flair():
		username = str(flair['user']).lower()
		if username in db:
			continue
		css = flair['flair_css_class']
		flair_text = flair['flair_text']
		if not flair_text:
			continue
		try:
			flair_count = int(flair_text.split(" ")[0])
		except:
			print("unable to parse count for user " + username + " with flair text " + flair_text)
			continue
		for _ in range(flair_count):
			d[username].append("LEGACY TRADE")
		count += 1
		if not count % 100:
			print("Finished adding " + str(count) + " users from the sub flair list")
	print(d)
	return d

def GetIdsFromPushshift(feedback_sub_name):
	print("Grabbing IDs from Pushshift")
	ids = set()
	authors = set()
	count = 0
	after = 0

	r = requests.get("https://api.pushshift.io/reddit/submission/search?subreddit=" + feedback_sub_name + "&after=" + str(after) + "&before=" + str(int(time.time()))  + "&size=100")
	data = r.json()['data']
	while data:
		for item in data:
			count += 1
			authors.add(str(item['author']).lower())

			item_time = 0
			if 'retrieved_on' in item:
				item_time = item['retrieved_on']
			if not 'retrieved_on' in item and 'created_utc' in item:
				item_time = item['created_utc']
			if item_time > after:
				after = item_time

			if 'id' in item:
				ids.add(item['id'])

			if 'selftext' in item:
				match = re.compile("r/" + feedback_sub_name + "/comments/(.*?)/")
				found = match.findall(item['selftext'].lower())
				for id_found in found:
					ids.add(id_found)

			if (count % 50 == 0):
				print("Total IDs Found: " + str(len(ids)))
				print("Current Date: " + time.strftime('%m/%d/%Y %H:%M:%S',  time.gmtime(after)))

		time.sleep(1)
		r = requests.get("https://api.pushshift.io/reddit/submission/search?subreddit=" + feedback_sub_name + "&after=" + str(after) + "&before=" + str(int(time.time()))  + "&size=100")
		data = r.json()['data']
	return ids, authors

def GetIdsFromReddit(sub, authors, ids):
	print("Grabbing IDs from Reddit")
	submission_count = 0
	for submission in sub.new(limit=1):
		ids.add(submission.id)
		authors.add(str(submission.author).lower())
		if sub.display_name.lower() == 'watchexchangefeedback':
			match = re.compile("\/*u\/([A-Za-z0-9_-]+)")
			found = match.findall(submission.title)
			if found:
				authors.add(str(found[0]).lower())
		submission_count += 1
		if submission_count % 50 == 0:
			print("Finished checking " + str(submission_count) + " search results from reddit.")

	author_count = 0
	for author in authors:
		author_count += 1
		time.sleep(0.5)
		for submission in sub.search("author:"+author):
			ids.add(submission.id)
		if sub.display_name.lower() == 'watchexchangefeedback':
			for submission in sub.search(author):
				ids.add(submission.id)
		if author_count % 10 == 0:
			print("Finished checking " + str(author_count) + " out of " + str(len(authors))  + " authors from reddit.")
	print("Found a total of " + str(len(ids)) + " post ids.")
	print(ids)

def GetUserCountsGCXRep(authors, ids, sub_config):
	print("Getting user counts from Reddit")
	d = defaultdict(lambda: [])

	count = 0
	ids_length = len(ids)
	for id in ids:
		count += 1
		if count%100==0:
			print(json.dumps(d))
			print("Checking " + str(count) + "/" + str(ids_length))
		time.sleep(0.5)
		try:
			submission = reddit.submission(id=id)
		except Exception as e:
			print("Found exception " + str(e) + "\n    Sleeping for 20 seconds...")
			time.sleep(20)
			submission = reddit.submission(id=id)
		try:
			author = str(submission.author).lower()
		except:
			print("Unable to get author from: " + str(id))
			continue
		comment_list = submission.comments
		try:
			comment_list.replace_more(limit=None)
		except:
			continue
		for comment in comment_list:
			correct_reply = None
			try:
				body = comment.body
			except:
				print("unable to get body from a comment on " + str(submission.permalink))
				continue
			potential_author_two = swap.get_username_from_text(body, [author])
			if potential_author_two:
				potential_author_two = potential_author_two.split("/")[1]
			else:
				continue
			replies = comment.replies
			try:
				replies.replace_more(limit=None)
			except:
				continue
			for reply in replies:
				try:
					found_author_name = str(reply.author).lower()
				except:
					found_author_name = ""
					print(str(submission.permalink) + " found a comment without an author, so skipping it...")
				if str(reply.author).lower() == potential_author_two:
					correct_reply = reply
			if correct_reply:
				d[author.lower()].append(potential_author_two.lower() + " - https://www.reddit.com" + str(submission.permalink)+str(comment.id))
	return d


def GetUserCountsWatchExchangeFeedback(authors, ids, sub_config):
	print("Getting user counts from Reddit")
	d = defaultdict(lambda: [])

	count = 0

	for id in ids:
		time.sleep(0.5)
		try:
			submission = reddit.submission(id=id)
		except Exception as e:
			print("Found exception " + str(e) + "\n    Sleeping for 20 seconds...")
			time.sleep(20)
			submission = reddit.submission(id=id)
		author = str(submission.author).lower()
		author2 = ""
                match = re.compile("\/*u\/([A-Za-z0-9_-]+)")
		found = match.findall(submission.title.lower())
		if found:
			author2 = found[0]
		else:
			for word in submission.title.lower().split(" "):
				if word in authors:
					author2 = word
					break
		# Not able to find a author in the title
		if not author2:
			continue
		if any(word in ["avoid", "bad", "difficult", "can't", "misrepresent", "waste", "scammer", "negative"] for word in submission.title.lower().split(" ")):
			# Negative Feedback
			continue
#		for comment in submission.comments:
#			giver = str(comment.author).lower()
#			comment_text = comment.body
#			while(" " in comment_text):
#				comment_text = comment_text.replace(" ", "")
#			for i in range(10):
#				comment_text = comment_text.replace(str(i), "1")
#			comment_text = comment_text.replace("1+", "+1")
#			if "+1" in comment_text:
#				d[author].append(giver + " - https://www.reddit.com" + str(comment.permalink))
		try:
			d[author.lower()].append(author2.lower() + " - https://www.reddit.com" + str(submission.permalink))
			d[author2.lower()].append(author.lower() + " - https://www.reddit.com" + str(submission.permalink))
		except Exception as e:
			print("Error encoding some text: ")
			try:
				print(author.lower())
				print(author2.lower())
				print(submission.permalink)
			except:
				print("Cant manage to print anything...")
		count += 1
		if count % 50 == 0:
			print("Finished looking at submission number " + str(count) + " out of " + str(len(ids)) + " submissions.")


	total_confirmations = sum([len(d[author]) for author in d])
	total_users = len(d.keys())
	print("Found " + str(total_confirmations) + " confirmations across " + str(total_users) + " total users.")
	print(d)
	return d

def UpdateDatabase(sub_name, users_to_confirmations):
	print("Updating Database for all users...")
	user_data = {}
	for user in users_to_confirmations:
		confirmation_text_list = ",".join(users_to_confirmations[user])
		user_data[user] = confirmation_text_list
	requests.post(request_url + "/add-batch-swap/", json={'sub_name': sub_name, 'platform': PLATFORM, 'user_data': user_data})

def UpdateFlairs(sub, sub_config, users):
	print("Updating flair for all users...")
	count = 0
        for user in users:
                swap_count = str(swap.get_swap_count(user, sub_config.gets_flair_from+[sub_config.database_name], PLATFORM))
                try:
                        swap.update_single_user_flair(sub, sub_config, user, swap_count, [], 0)
                except Exception as e:
                        print("Found exception " + str(e) + "\n    Sleeping for 20 seconds...")
                        time.sleep(20)
			try:
	                        swap.update_single_user_flair(sub, sub_config, user, swap_count, [])
			except Exception as e:
				print("Unable to assign flair to " + user + ":\n    " + str(e))
                time.sleep(0.5)
		count += 1
		if count % 25 == 0:
			print("Finished assigning flair for " + str(count) + " users out of " + str(len(users)) + " users.")

sub_config = config.Config(sub_name)
reddit = praw.Reddit(client_id=sub_config.client_id, client_secret=sub_config.client_secret, user_agent='UserAgent', username=sub_config.bot_username, password=sub_config.bot_password)
sub = reddit.subreddit(sub_config.subreddit_name)
feedback_sub = reddit.subreddit(feedback_sub_name)


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



## Use this for backfilling from feedback subs
#ids, authors = GetIdsFromPushshift(feedback_sub_name)
ids = set([])
authors = set(["chewy_ube".lower()])
GetIdsFromReddit(feedback_sub, authors, ids)
users_to_confirmations = GetUserCountsGCXRep(authors, ids, sub_config)
#users_to_confirmations = GetUserCountsWatchExchangeFeedback(authors, ids, sub_config)

## Use this for backfilling based on flair
#users_to_confirmations = GetUserToCss(sub)

## Use this for manual count assignment
#users_to_confirmations = {"zcheryl".lower(): ["LEGACY TRADE"] * 1}
#users_to_confirmations = {"HerbyVershmales".lower(): ["avoidingwork57 - https://www.reddit.com/r/WatchExchangeFeedback/comments/fpahsn"]}

UpdateDatabase(sub_config.subreddit_name, users_to_confirmations)
UpdateFlairs(sub, sub_config, users_to_confirmations.keys())
