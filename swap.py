import random
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'Discord')
from assign_role import assign_role
import Config
import requests
import re
import json
import praw
from praw.models import SubredditHelper
from prawcore.exceptions import NotFound
import time
import datetime
import argparse
import wiki_helper

debug = False
silent = False

PLATFORM = "reddit"
CREDIT_ALREADY_GIVEN_TEXT = "I already have a reference to this trade in my database. This can mean one of three things:\n\n* You made two 'different' transactions with one person in this post and expect to get +2 in your flair for it. However, users are only allowed one confirmation per partner per post. Sorry for the inconevnience, but there are no exceptions.\n\n* You or your partner already tried to confirm this transaction in this post already\n\n* Reddit was having issues earlier and I recorded the transaction but just now got around to replying and updating your flair.\n\nRegardless of which situation applies here, both you and your partner's flairs are all set and no further action is required from either of you. Thank you!"

def log(post, comment, reason):
	url = "reddit.com/comments/"+str(post)+"/-/"+str(comment)
	print("Removing comment " + url + " because: " + reason)

def create_reddit_and_sub(sub_name):
	sub_config = Config.Config(sub_name.lower())
	if not all([sub_config.client_id, sub_config.client_secret, sub_config.refresh_token]):
		return sub_config, None, None
	reddit = sub_config.reddit_object
	sub = sub_config.subreddit_object
	return sub_config, reddit, sub

request_url = "http://0.0.0.0:8000"

check_time = datetime.datetime.utcnow().time()

kofi_text = "\n\n---\n\n[^(Buy the developer a coffee)](https://kofi.regexr.tech) ^or [^(support this project monthly)](https://patreon.regexr.tech)"

def get_comment_text(comment):
	body = comment.body.lower().strip()
	while("\\" in body):
		body = body.replace("\\", "")
	body = body.replace("www.reddit.com/user/", "www.reddit.com/u/")
	return body

# Checks if the time at script start up is between two desired times
def is_time_between(begin_time, end_time):
	if begin_time < end_time:
		return check_time >= begin_time and check_time <= end_time
	else: # crosses midnight
		return check_time >= begin_time or check_time <= end_time

# Method for giving credit to users when they do a trade.
# Returns True if credit was given, False otherwise
def update_database(author1, author2, post_id, comment_id, sub_config, top_level_comment_id=""):
	author1 = str(author1).lower()  # Create strings of the user names for keys and values
	author2 = str(author2).lower()
	r = requests.post(request_url + "/check-comment/", {'sub_name': sub_config.database_name, 'author1': author1, 'author2': author2, 'post_id': post_id, 'comment_id': comment_id,'top_level_comment_id': top_level_comment_id,  'real_sub_name': sub_config.subreddit_name, 'platform': PLATFORM})
	try:
		return_data = r.json()
	except Exception as e:
		print("ERROR: Unable to update database for r/" + sub_config.database_name + " for u/" + author1 + " and u/" + author2 + " with post ID " + post_id + " and comment ID " + comment_id + " and top_level_comment_id " + top_level_comment_id + " on platform " + PLATFORM + " with error " + str(e))
		return True
	# If at least one confirmation was not a duplicate, credit was given
	return any([return_data[username]['is_duplicate'] == 'False' for username in return_data])

def get_flair_template(templates, count):
	if not templates:
		return ""
	keys = [int(x) for x in templates.keys()]
	keys.sort()
	template = ""
	for key in keys:
		if key > count:
			break
		template = templates[str(key)]
	return template

def get_age_title(age_titles, age):
	if not age_titles:
		return ""
	keys = [int(x) for x in age_titles.keys()]
	keys.sort()
	age_title = ""
	for key in keys:
		if key > age:
			break
		age_title = age_titles[str(key)]
	return age_title

def get_discord_role(roles, count):
	if not roles:
		return ""
	keys = [int(x) for x in roles.keys()]
	keys.sort()
	role_id = ""
	for key in keys:
		if key > count:
			break
		role_id = roles[str(key)]
	return role_id

def get_swap_count(author_name, subs, platform):
	return_data = requests.get(request_url + "/get-user-count-from-subs/", data={'sub_names': ",".join(subs), 'current_platform': platform, 'author': author_name.lower()}).json()
	return int(return_data['count'])

def update_flair(author1, author2, sub_config):
	"""
	returns list of tuples of author name and (str)swap count if flair was NOT updated.
	also returns a dict of usernames to flair text
	"""
	non_updated_users = []
	user_flair_text = {}
	# Loop over each author and change their flair
	for author in [author1, author2]:
		if not author:
			continue
		try:
			age = datetime.timedelta(seconds=(time.time() - author.created_utc)).days
		except Exception as e:
			print("Unable to get age for " + str(author) + " with error " + str(e) + ". As such, I am unable to update their flair.")
			continue
		author_string = str(author).lower()
		updates = []
		for sub_name in [sub_config.subreddit_name] + sub_config.gives_flair_to:
			if sub_name not in sub_config.sister_subs:
				sister_sub_config = Config.Config(sub_name.lower())
				sister_reddit = sister_sub_config.reddit_object
				sister_sub = sister_sub_config.subreddit_object
				sub_config.sister_subs[sub_name] = {'reddit': sister_reddit, 'sub': sister_sub, 'config': sister_sub_config}
			author_count = str(get_swap_count(author_string, [sub_name] + sub_config.sister_subs[sub_name]['config'].gets_flair_from, PLATFORM))
			flair_text = update_single_user_flair(sub_config.sister_subs[sub_name]['sub'], sub_config.sister_subs[sub_name]['config'], author_string, author_count, non_updated_users, age, debug)
			if flair_text:
				updates.append([sub_name, flair_text])
				if sub_name == sub_config.subreddit_name:
					user_flair_text[author_string] = flair_text
		if updates:
			try:
				print("u/" + author_string + " was updated at the following subreddits with the following flair: \n" + "\n".join(["  * r/"+x[0]+" - "+x[1] for x in updates]))
			except Exception as e:
				print("Unable to log " + author_string + " flair update with error " + str(e))
	return non_updated_users, user_flair_text

def update_single_user_flair(sub, sub_config, author, swap_count, non_updated_users, age, debug=False):
	"""
	Updates a user's flair.
	Returns the flair text of the user.
	"""
	try:
		mods = [str(x).lower() for x in sub.moderator()]
	except Exception as e:
		print("Unable to get mod list from " + sub_config.subreddit_name + " with error " + str(e))
		return ""
	if author.lower() in sub_config.black_list:
		return "" # Silently return
	if int(swap_count) < sub_config.flair_threshold:
		non_updated_users.append((author, swap_count))
		return ""
	template = get_flair_template(sub_config.flair_templates, int(swap_count))
	title = get_flair_template(sub_config.titles, int(swap_count))
	age_title = get_age_title(sub_config.age_titles, age)
	discord_role_id = get_discord_role(sub_config.discord_roles, int(swap_count))
	flair_text = ""
	if not debug:
		# Only non-mods and mods when display count is enabled get counts in their flair
		if author not in mods or sub_config.display_mod_count:
			if swap_count == "1" and sub_config.flair_word[-1] == 's':
				flair_text = swap_count + " " + sub_config.flair_word[:-1]
			else:
				flair_text = swap_count + " " + sub_config.flair_word
		if author in mods and sub_config.mod_flair_word:
			template = sub_config.mod_flair_template
			if flair_text:
				flair_text = sub_config.mod_flair_word + " | " + flair_text
			else:
				flair_text = sub_config.mod_flair_word
		if title:
			if age_title:
				flair_text += " | " + age_title + " " + title
			else:
				flair_text += " | " + title
		try:
			if template:
				sub.flair.set(redditor=author, text=flair_text, flair_template_id=template)
			else:
				sub.flair.set(redditor=author, text=flair_text, css_class=swap_count)
		except Exception as e:
			print("Error assigning flair to " + str(author) + " on sub " + sub_config.subreddit_name + " with error " + str(e) + ". Please update flair manually.")
		if sub_config.discord_config and discord_role_id:
			paired_usernames = requests.get(request_url + "/get-paired-usernames/").json()
			if author in paired_usernames['reddit']:
				discord_user_id = paired_usernames['reddit'][author]['discord']
				assign_role(sub_config.discord_config.server_id, discord_user_id, discord_role_id)
	else:
		print("Assigning flair " + swap_count + " to user " + author + " with template_id: " + template)
		print("==========")
	return flair_text

def set_active_comments_and_messages(reddit, sub, bot_name, comments, messages, new_ids, sub_config):
	# Cache the comment objects so we can reuse them later.
	ids_to_comments = {}
	# Get comments from username mentions
	ids = []
	to_mark_as_read = []
	try:
		for message in reddit.inbox.unread():
			to_mark_as_read.append(message)
			if message.was_comment and message.subject == "username mention" and (not str(message.author).lower() == "automoderator"):
				try:
					ids.append(message.id)
					ids_to_comments[id] = message
				except:  # if this fails, the user deleted their account or comment so skip it
					pass
			elif not message.was_comment:
				if 'gadzooks! **you are invited to become a moderator**' in message.body.lower() and message.subreddit != None and message.subreddit.display_name.lower() == sub_config.subreddit_name:
					try:
						sub_config.subreddit_object.mod.accept_invite()
					except Exception as e:
						print("Was unable to accept invitation to moderate " + sub_config.subreddit_name + " with error " + str(e))
						continue
					# This means that we're in action for the first time, so let's also claim our own subreddit
					print("Attempting to claim r/" + sub_config.bot_username)
					sh = SubredditHelper(sub_config.reddit_object, {})
					try:
						sh.create(sub_config.bot_username, subreddit_type='private')
					except Exception as e:
						if 'SUBREDDIT_EXISTS' in str(e):
							print("    IMPERSONATION FOUND FOR u/" + sub_config.bot_username)
				else:
					messages.append(message)
	except Exception as e:
		print(e)
		print("Failed to get next message from unreads. Ignoring all unread messages and will try again next time.")

	# Get comments by parsing the most recent comments on the sub.
	try:
		new_comments = sub.comments(limit=20)
		for new_comment in new_comments:
			try:
				new_comment.refresh()
			except: # if we can't refresh a comment, ignore it.
				continue
			# If this comment is tagging the bot, we haven't seen it yet, and the bot has not already replied to it, we want to track it.
			if "u/"+bot_name.lower() in new_comment.body.lower() and new_comment.id not in ids and not str(new_comment.author).lower() == "automoderator":
				bot_reply = find_correct_reply(new_comment, str(new_comment.author), "u/"+bot_name.lower(), None)
				if not bot_reply:
					ids.append(new_comment.id)
					ids_to_comments[new_comment.id] = new_comment
	except Exception as e:
		print(e)
		print(bot_name + " failed to get most recent comments.")

	return_data = requests.post(request_url + "/get-comments/", {'sub_name': sub_config.subreddit_name, 'active': 'True', 'ids': ",".join(ids), 'platform': PLATFORM}).json()
	ids = return_data['ids']
	new_ids += return_data['new_ids']
	for comment_id in ids:
		try:
			if comment_id in ids_to_comments:
				comment = ids_to_comments[comment_id]
			else:
				comment = reddit.comment(comment_id)
			comments.append(comment)
		except Exception as e:  # If we fail, the user deleted their comment or account, so skip
			print("Failed to turn comment id " + comment_id + " into a comment object with bot " + bot_name + " with error " + str(e))
			pass

	if not debug:
		for message in to_mark_as_read:
			try:
				message.mark_read()
			except Exception as e:
				print(e)
				print("Unable to mark message as read. Leaving it as is.")

def set_archived_comments(reddit, comments, sub_config):
	ids = ",".join([comment.id for comment in comments])
	# Cache the comment objects so we can reuse them later.
	ids_to_comments = {}
	for comment in comments:
		ids_to_comments[comment.id] = comment
	all_ids = requests.post(request_url + "/get-comments/", {'sub_name': sub_config.subreddit_name, 'active': 'False', 'ids': ids, 'platform': PLATFORM}).json()['ids']
	for id in all_ids:
		if id not in ids: # if this was not already passed in
			if id in ids_to_comments:
				comment = ids_to_comments[id]
			else:
				comment = reddit.comment(id)
			comments.append(comment)

def comment_is_too_early(comment, post, top_level_comment, sub_config):
	if str(post.author).lower() == "automoderator":
		post_time = top_level_comment.created_utc
	else:
		post_time = post.created_utc
	# post_age_threshold is measured in days
	threshold_seconds = sub_config.post_age_threshold * 24 * 60 * 60
	comment_time = comment.created_utc
	if (comment_time - post_time) < threshold_seconds:
		return True
	return False

def handle_comment(comment, bot_username, sub, reddit, is_new_comment, sub_config):
	# Get an instance of the parent post
	parent_post = comment
	top_level_comment = comment
	while parent_post.__class__.__name__ == "Comment":
		top_level_comment = parent_post
		parent_post = parent_post.parent()
	try:
		parent_sub = parent_post.subreddit
	except Exception as e:  # If we can't get the sub, it means the sub is private.
		log(parent_post, comment, "Associated sub is private. Error: " + str(e))
		requests.post(request_url + "/archive-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
#		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# r/edefinition keeps the bot around as a pet. Have some fun with them here.
	if str(parent_sub).lower() == "edefinition":
		print("ALERT! r/edefinition post: redd.it/" + str(parent_post))
		handle_edefinition(comment)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# If this is someone responding to a tag by tagging the bot, we want to ignore them.
	if isinstance(comment.parent(), praw.models.Comment) and bot_username.lower() in comment.parent().body.lower() and 'automod' not in str(comment.parent().author).lower():
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# Remove comments made by shadowbanned users.
	if comment.banned_by:
		log(parent_post, comment, "Comment was made by a shadow banned user")
		handle_comment_by_filtered_user(comment)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	author1 = comment.author  # Author of the top level comment
	comment_text = get_comment_text(comment)
	# Determine if they properly tagged a trade partner
	desired_author2_string = get_username_from_text(comment_text, [bot_username, str(author1)])
	if not desired_author2_string:
		log(parent_post, comment, "No other user was tagged in the comment.")
		handle_no_author2(comment)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# Remove comment if author2 is not a real reddit account
	try:
		reddit.redditor(desired_author2_string.split("/")[1]).id
	except NotFound:
		log(parent_post, comment, "Tagged user " + desired_author2_string + " is not a real username.")
		handle_no_redditor(comment, desired_author2_string)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	except AttributeError:
		log(parent_post, comment, "Tagged user " + desired_author2_string + " is a suspended account.")
		handle_suspended_redditor(comment)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	except Exception as e:
		print("Could not make a reddit instance with an ID for reddit account: " + desired_author2_string + " with error: " + str(e))
	# Remove comments that are in the wrong sub
	if not str(parent_post.subreddit).lower() == sub_config.subreddit_name.lower():
		log(parent_post, comment, "Wrong sub - in " + str(parent_post.subreddit).lower() + ", should be in " + sub_config.subreddit_name.lower())
		handle_wrong_sub(comment)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# Remove comments in giveaway posts
	if "(giveaway)" in parent_post.title.lower():
		log(parent_post, comment, "Post is a giveaway")
		handle_giveaway(comment)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# Remove comment if post is archived
	if parent_post.archived:
		log(parent_post, comment, "Post is archived")
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# Remove comment if the author of the post has deleted the post
	if not parent_post.author:
		log(parent_post, comment, "Post is deleted")
		handle_deleted_post(comment)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# Remove comment if post has been removed by a moderator
	if not parent_post.is_robot_indexable:
		log(parent_post, comment, "Post was removed by a moderator.")
		handle_comment_on_removed_post(comment)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# Handle confirmations in automod threads
	if str(parent_post.author).lower() == "automoderator":
		# Confirmations in Automod threads must not be done at the top level.
		if comment == top_level_comment:
			handle_top_level_in_automod(comment)
			log(parent_post, comment, "Top level comment in automod post.")
			requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
			return True
		# Remove comment if neither the person doing the tagging nor the person being tagged are the OP of the top level comment
		if not str(author1).lower() == str(top_level_comment.author).lower() and not "u/"+str(top_level_comment.author).lower() == desired_author2_string.lower():
			log(parent_post, comment, "Neither participant is OP")
			handle_not_op(comment, str(top_level_comment.author), desired_author2_string.split("/")[-1])
			requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
			return True
	# Remove comment if neither the person doing the tagging nor the person being tagged are the OP
	elif not str(author1).lower() == str(parent_post.author).lower() and not "u/"+str(parent_post.author).lower() == desired_author2_string.lower():
		log(parent_post, comment, "Neither participant is OP")
		handle_not_op(comment, str(parent_post.author), desired_author2_string.split("/")[-1])
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# Remove comment if the difference between the post time of the submission and comment are less than the post_age_threshold
	if comment_is_too_early(comment, parent_post, top_level_comment, sub_config):
		log(parent_post, comment, "Comment was made too early")
		handle_comment_made_too_early(comment)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	# Remove comment if the post title contains a blacklisted word
	if any([x.lower() in parent_post.title.lower() for x in sub_config.title_black_list]):
		type = ""
		for word in sub_config.title_black_list:
			if word.lower() in parent_post.title.lower():
				type = word
		log(parent_post, comment, "Comment was made on a blacklisted post of type " + type)
		handle_comment_on_blacklisted_post(comment, type)
		requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True

	correct_reply = find_correct_reply(comment, author1, desired_author2_string, parent_post)
	if correct_reply:
		# If we already left a comment saying we updated their flair, ignore this.
		bot_reply = find_correct_reply(correct_reply, desired_author2_string, sub_config.bot_username, parent_post)
		if bot_reply and any([x in bot_reply.body for x in [' -> ', CREDIT_ALREADY_GIVEN_TEXT]]):
			log(parent_post, comment, "Bot found it again for some reason")
			requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
			return True
		# Remove if correct reply is made by someone who cannot leave public commens on the sub
		if correct_reply.banned_by:
			log(parent_post, comment, "Replying user is shadow banned")
			handle_reply_by_filtered_user(comment)
			requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
			return True
		author2 = correct_reply.author
		if debug:
			print("Author1: " + str(author1))
			print("Author2: " + str(author2))

		if correct_reply.is_submitter or comment.is_submitter:  # make sure at least one of them is the OP for the post
			credit_given = update_database(author1, author2, parent_post.id, comment.id, sub_config)
		elif str(parent_post.author).lower() == "automoderator":
			credit_given = update_database(author1, author2, parent_post.id, comment.id, sub_config, top_level_comment.id)
		else:
			credit_given = False

		if credit_given:
			non_updated_users, user_flair_text = update_flair(author1, author2, sub_config)
			inform_giving_credit(correct_reply, non_updated_users, sub_config, user_flair_text)
		else:
			log(parent_post, comment, "Credit already given")
			non_updated_users, user_flair_text = update_flair(author1, author2, sub_config)
			inform_credit_already_given(correct_reply)
			requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
		return True
	else:  # If we found no correct looking comments, let's come back to it later
		# New comments get auto response so users know they've been heard
		if is_new_comment:
			inform_comment_tracked(comment, desired_author2_string, parent_post, sub_config.subreddit_name, str(author1))
		if debug:
			print("No correct looking replies were found")
		return False

def get_username_from_text(text, usernames_to_ignore=[]):
	text = text.replace("/user/", "/u/")
	pattern = re.compile("u\/([A-Za-z0-9_-]+)")
	found = re.findall(pattern, text)
	username = ""
	for found_username in found:
		if found_username not in [x.lower() for x in usernames_to_ignore] + ['digitalcodesellbot', 'uvtrade_bot', 'airsoftmarketbot', 'airsoftswapbot', 'c4c_bot', 'acamiibobot']:
			username = "u/" + found_username
			break
	return username.lower()

def reply(comment, reply_text):
	try:
		if not debug:
			if not silent:
				reply = comment.reply(reply_text+kofi_text)
				reply.mod.lock()
			else:
				print(reply_text + "\n==========")
		else:
			print(reply_text + "\n==========")
	except Exception as e:  # Comment was probably deleted
		print(e)
		print("    Comment: " + str(comment))

def handle_no_author2(comment):
	reply_text = "You did not tag anyone other than this bot in your comment. Please post a new top level comment tagging this bot and the person you traded with to get credit for the trade."
	reply(comment, reply_text)

def handle_comment_on_removed_post(comment):
	reply_text = "Sorry, but the post you just commented on was removed by a moderator. Removed posts cannot be used to confirm transactions. If you believe this post was removed in error, please reach out to the mods via mod mail to get it approved. Otherwise, please try again on a post that has not been removed. Thanks!"
	reply(comment, reply_text)

def handle_deleted_post(comment):
	reply_text = "The OP of this submission has deleted the post. As such, this bot cannot verify that either you or the person you tagged are the OP of this post. No credit can be given for this trade because of this. Please do not delete posts again in the future. Thanks!"
	reply(comment, reply_text)

def handle_wrong_sub(comment):
	reply_text = "Whoops! Looks like you tagged me in the wrong subreddit. If you meant to tag a different bot, please **EDIT** this comment, remove my username, and tag the correct bot instead. If you meant to tag me, please make a new comment in the sub where I operate. Thanks!"
	reply(comment, reply_text)

def handle_edefinition(comment):
	# No more peeking
	f = open("edefinition.txt", "r")
	reply_options = [x for x in f.read().splitlines() if x[0] != "#"]
	f.close()
	random.seed()
	reply_text = random.choice(reply_options)
	reply(comment, reply_text)

def handle_comment_on_blacklisted_post(comment, type):
	reply_text = "Sorry, but I am not allowed to confirm transactions on " + type + " posts. Please try again on another post. Thanks!"
	reply(comment, reply_text)

def handle_comment_made_too_early(comment):
	reply_text = "You tried to confirm a transaction too quickly! Please make sure that all transactions are confirmed **AFTER** *both* parties have received their end of the deal. **NOT BEFORE**. Please feel free to try confirming again at a later date. This comment will no longer be tracked. Thanks!"
	reply(comment, reply_text)

def handle_giveaway(comment):
	reply_text = "This post is marked as a (giveaway). As such, it cannot be used to confirm any transactions as no transactions have occured. Giveaways are not valid for increasing your feedback score. This comment will not be tracked and no feedback will be given."
	reply(comment, reply_text)

def handle_top_level_in_automod(comment):
	reply_text = "Confirmations done in a thread authored by Automoderator should be done as replies to the comment where the transaction originated, **NOT** as top level replies to the post. Please make a new comment replying to the original comment in this thread that initiated the transaction. Thank you!"
	reply(comment, reply_text)

def handle_not_op(comment, op_author, incorrect_name):
	reply_text = "Neither you nor the person you tagged are the OP of this post so credit will not be given and this comment will no longer be tracked. The original author is `" + op_author.lower() + "` but you tagged `" + incorrect_name + "`. If you meant to tag someone else, please make a **NEW** comment and tag the correct person (**editing your comment will do nothing**). Thanks!"
	reply(comment, reply_text)

def handle_comment_by_filtered_user(comment):
	reply_text = "Thank you for tagging the Confirmation Bot. Unfortunately, you are not allowed to participate in the sub at this time. As such, we cannot confirm transactions between you and your partner. Please try participating again once you meet this sub's participation requirements."
	reply(comment, reply_text)

def handle_reply_by_filtered_user(comment):
	reply_text = "The person you are attempting to confirm a trade with is unable to leave public comments on this sub. As such, this trade cannot be counted. Sorry for the inconvenience."
	reply(comment, reply_text)

def handle_no_redditor(comment, tagged_username):
	reply_text = "The person you tagged, " + tagged_username + ", is not a real redditor. You can verify this by clicking the tag. This most likely means you misspelled your partner's name **OR** they deleted their account. If you made a spelling mistake, please make a **NEW** comment with the correct spelling. *Editing* this comment will do nothing. If your partner has deleted their account, you will NOT be able to confirm your transaction. Sorry for the inconvenience."
	reply(comment, reply_text)

def handle_suspended_redditor(comment):
	reply_text = "The person you tagged has had their reddit account suspended by the Reddit site-wide Admins. As such, this person will not be able to confirm a transaction with you. If their account is unsuspended, you will need to make a new comment to confirm a transaction with them as **this comment will no longer be tracked**."
	reply(comment, reply_text)

def inform_comment_tracked(comment, desired_author2_string, parent_post, sub_name, tagging_user):
	reply_text = "This comment is now being tracked. Your flair will update once your partner replies to your comment.\n\n" + desired_author2_string + ", please reply to the above comment with your feedback **ONLY AFTER YOUR TRANSACTION IS COMPLETE** and *both* sides have received their end of the transaction. Once you reply, you will both get credit and your flair scores will increase.\n\n" + desired_author2_string + ", if you did **NOT** complete a transaction with this person, please **DO NOT** reply to their comment as this will confirm the transaction. Instead, please [message the moderators](https://www.reddit.com/message/compose/?to=r/" + sub_name + "&subject=Incorrectly%20Tagged%20Confirmation&message=u%2F" + tagging_user + "%20incorrectly%20tagged%20me%20in%20this%20comment%3A%20https%3A%2F%2Fwww.reddit.com%2Fcomments%2F" + parent_post.id + "%2F-%2F" + comment.id + ") so we can contact the user and handle the situation.\n\nThank you!"
	reply(comment, reply_text)

def inform_credit_already_given(comment):
	reply(comment, CREDIT_ALREADY_GIVEN_TEXT)

def inform_comment_archived(comment, sub_config):
	comment_text = get_comment_text(comment)
	author2 = get_username_from_text(comment_text, [sub_config.bot_username, str(comment.author)])
	reply_text = author2 + ", please reply to the comment above once both parties have received their end of the transaction to confirm with your trade partner.\n\nThis comment has been around for more than a day without a response. The bot will still track this comment but it will only check it once a day. This means that if your trade partner replies to your comment, it will take up to 24 hours before your comment is confirmed. Please wait that long before messaging the mods for help. If you are getting this message but your partner has already confirmed, please message the mods for assistance."
	reply(comment, reply_text)

def inform_comment_deleted(comment):
	reply_text = "This comment has been around for more than a week and will no longer be tracked. If you wish to attempt to get trade credit for this swap again, please make a new comment and tag both this bot and your trade partner."
	reply(comment, reply_text)

def inform_giving_credit(comment, non_updated_users, sub_config, user_flair_text):
	reply_text = sub_config.confirmation_text
	if non_updated_users:
		reply_text += "\n\n---\n\nThis trade **has** been recorded for **both** users in the database. However, the following user(s) have a total number of " + sub_config.flair_word.lower() + " that is below the threshold of " + str(sub_config.flair_threshold) + " and have **not** had their flair updated:"
		for user, swap_count in non_updated_users:
			reply_text += "\n\n* " + user + " - " + swap_count + " " + sub_config.flair_word
		reply_text += "\n\nFlair for those users will update only once they reach the flair threshold mentioned above."
	if user_flair_text:
		reply_text += "\n\n---\n\n" + "\n".join(["* u/" + user + " -> " + flair_text for user, flair_text in user_flair_text.items()])
	reply(comment, reply_text)

def reply_to_message(message, text, sub_config):
	if not debug:
		try:
			if not silent:
				message.reply(text + kofi_text)
			else:
				print(text + "\n==========")
		except Exception as e:
			print(sub_config.bot_username + " could not reply to " + str(message.author) + " with error...")
			print("    " + str(e))
	else:
		print(text + "\n==========")

def format_swap_count(trades_data, sub_config):
	final_text = ""
	legacy_count = 0
	for platform in trades_data:
		if 'legacy_count' in trades_data[platform]:
			legacy_count += trades_data[platform]['legacy_count']
		for trade in trades_data[platform]['transactions'][::-1]:
			if platform == 'reddit':
				trade_partner = trade['partner']
				trade_partner_count = get_swap_count(trade_partner, [sub_config.database_name], PLATFORM)
				if trade['comment_id']:
					trade_url = "https://www.reddit.com/r/" + sub_config.database_name + "/comments/" + trade['post_id'] + "/-/" + trade['comment_id']
				else:
					trade_url = "https://redd.it/" + trade['post_id']
				trade_url_sub = sub_config.subreddit_display_name
				final_text += "*  [" + trade_url_sub + "/" + trade['post_id']  + "](https://" + trade_url  + ") - u/" + trade_partner + " (Has " + str(trade_partner_count) + " " + sub_config.flair_word + ")" + "\n\n"
			elif platform == 'discord':
				trade_url = "https://www.discord.com/channels/" + str(sub_config.discord_config.server_id) + "/" + trade['post_id'] + "/" + trade['comment_id']
				final_text += "* [Discord " + sub_config.flair_word[:-1] + "](" +  trade_url + ")\n\n"
			else:
				print("Found unexpected platform `" + platform + "` when running `format_swap_count` for sub " + sub_config.subreddit_display_name)
				continue

	if legacy_count > 0:
		final_text = "* " + str(legacy_count) + " Legacy Trades (trade done before this bot was created)\n\n" + final_text

	return final_text


def find_correct_reply(comment, author1, desired_author2_string, parent_post):
	replies = comment.replies
	try:
		replies.replace_more(limit=None)
	except Exception as e:
		print("Was unable to add more comments down the comment tree when trying to find correct reply with comment: " + str(comment) + " with error: " + str(e) + "\n    parent post: " + str(parent_post) + "\n    author1: " + str(author1) + "\n    author2: u/" + desired_author2_string)
#		return None
	for reply in replies.list():
		try:
			potential_author2_string = "u/"+str(reply.author).lower()
		except:
			# This is sometimes a more comments object
			continue
		if not potential_author2_string == desired_author2_string:
			continue
		if str(author1).lower() == potential_author2_string:  # They can't get credit for swapping with themselves
			continue
		return reply
	return None

def handle_manual_adjustment(message, sub_config):
	error_text = "\n\nPlease send a message in the form of `$add u/<requester> u/<unresponsive_user> <reddit link>` and try again (don't include the `<>` characters)."

	requesting_mod = message.author.name.lower()
	if requesting_mod not in sub_config.admins:
		reply_text = "Error: You are not authorized to execute this command." + error_text
		return reply_to_message(message, reply_text, sub_config)

	items = message.body.split(" ")
	if len(items) < 4:
		response_text = "Error: Invalid Format." + error_text
		return reply_to_message(message, reply_text, sub_config)

	username1 = items[1]
	username2 = items[2]
	link = items[3]
	if all(['u/' not in x for x in [username1, username2]]):
		response_text = "Error: No usernames could be found in the message you sent." + error_text
		return reply_to_message(message, reply_text, sub_config)
	if any(['u/' not in x for x in [username1, username2]]):
		response_text = "Error: Only one username was found." + error_text
		return reply_to_message(message, reply_text, sub_config)
	username1 = username1.split("/")[-1].lower()
	username2 = username2.split("/")[-1].lower()

	url_parts = link.split("/")
	if len(url_parts) < 8:
		reply_text = "Error: Could not find a proper reddit URL in the message. Please ensure the URL looks like this: https://www.reddit.com/r/subreddit/comments/xxxxxxx/.../xxxxxxx" + error_text
		return reply_to_message(message, reply_text, sub_config)
	post_id = url_parts[6]
	comment_id = url_parts[8]
	thread = "https://www.reddit.com/r/" + sub_config.subreddit_name + "/comments/" + post_id
	post_object = sub_config.reddit_object.submission(id=post_id)

	try:
		attempted_sub_name = post_object.subreddit.display_name.lower()
		if sub_config.subreddit_name != attempted_sub_name:
			reply_text = "Error: I am not supposed to run on r/" + attempted_sub_name + error_text
			return reply_to_message(message, reply_text, sub_config)
	except Exception as e:
		reply_text = "Error: " + str(e) + error_text
		return reply_to_message(message, reply_text, sub_config)

	if post_object.author.name.lower() not in [username1, username2]:
		reply_text = "Error: Neither u/" + username1 + " nor u/" + username2 + " are the author of " + thread + "\n\nThe author of that thread is u/" + post_object.author.name + error_text
		return reply_to_message(message, reply_text, sub_config)

	user_data = [{'post_id': post_id, 'comment_id': comment_id, 'partner': username2, 'timestamp': int(time.time())}]
	return_data = requests.post(request_url + "/add-batch-swap/", json={'sub_name': sub_config.subreddit_name, 'platform': 'reddit', 'user_data': {username1: user_data}}).json()
	if return_data[username1] == 'False':
		reply_text = "Error: This transaction was previously recorded for u/" + username1
		return reply_to_message(message, reply_text, sub_config)

	# Send a notification if someone other than RegExr uses this feature.
	if requesting_mod != 'regexr':
		try:
			sub_config.subreddit_object.message(subject="[Notification] Manual Flair Update", message="u/" + message.author.name + " has manually updated flair for u/" + username1 + " because u/" + username2 + " was unresponsive in thread " + thread)
		except Exception as e:
			print("Unable to send mod mail message to r/" + sub_config.subreddit_display_name + " with subject\n\n" + subject + "\n\n and body\n\n" + body)

	update_flair(sub_config.reddit_object.redditor(username1), None, sub_config)

	return reply_to_message(message, "Success!", sub_config)

def handle_swap_data_request(message, sub_config):
	text = (message.body + " " +  message.subject).replace("\n", " ").replace("\r", " ")
	username = get_username_from_text(text)[2:]  # remove the leading u/ in the username
	if not username:  # If we didn't find a username, let them know and continue
		reply_text = "Hi there,\n\nYou did not specify a username to check. Please ensure that you have a user name in the body of the message you just sent me. Please feel free to try again. Thanks!"
		reply_to_message(message, reply_text, sub_config)
		return
	trades_data = requests.post(request_url + "/get-summary/", {'sub_name': sub_config.database_name, 'current_platform': PLATFORM, 'username': username}).json()['data']
	trade_count = 0
	for platform in trades_data:
		trade_count += len(trades_data[platform]['transactions'])
		if 'legacy_count' in trades_data[platform]:
			trade_count += trades_data[platform]['legacy_count']
	# Text based on swaps for this sub
	if trade_count == 0:
		reply_header = "Hello,\n\nu/" + username + " has not had any " + sub_config.flair_word + " in this sub yet."
		swap_count_text = ""
	else:
		reply_header = "Hello,\n\nu/" + username + " has had the following " + str(trade_count) + " " + sub_config.flair_word + ":\n\n"
		swap_count_text = format_swap_count(trades_data, sub_config)
	# Get a summary of other subs at the bottom of the message
	sister_sub_text = ""
	for sister_sub in sub_config.gets_flair_from:
		sister_sub_count = get_swap_count(username, [sister_sub], PLATFORM)
		if sister_sub_count > 0:
			sister_sub_text += "\n\nThis user also has " + str(sister_sub_count) + " " + sub_config.flair_word + " on r/" + sister_sub
	# Truncate if too large
	if len(reply_header+swap_count_text+sister_sub_text+kofi_text) > 10000:
		truncated_text = "* And more..."
		amount_to_truncate = len(reply_header+swap_count_text+sister_sub_text+kofi_text+truncated_text) + 1 - 10000
		swap_count_text = swap_count_text[:len(swap_count_text) - amount_to_truncate]
		swap_count_text = "*".join(swap_count_text.split("*")[:-1])
	else:
		truncated_text = ""

	reply_text = reply_header + swap_count_text + truncated_text + sister_sub_text

	reply_to_message(message, reply_text, sub_config)


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('sub_name', metavar='C', type=str)
	args = parser.parse_args()

	sub_config = Config.Config(args.sub_name.lower())
	reddit = sub_config.reddit_object
	sub = sub_config.subreddit_object
	sub_config.sister_subs[sub_config.subreddit_name] = {'reddit': reddit, 'sub': sub, 'config': sub_config}

	wiki_helper.run_config_checker(sub_config)

	comments = []  # Stores comments from both sources of Ids
	messages = []  # Want to catch everything else for replying
	new_ids = []  # Want to know which IDs are from comments we're just finding for the first time
	set_active_comments_and_messages(reddit, sub, sub_config.bot_username, comments, messages, new_ids, sub_config)

	# Process comments
	if debug:
		print("Looking through active comments...")
	for comment in comments:
		try:
			comment.refresh()  # Don't know why this is required but it doesnt work without it so dont touch it
		except: # if we can't refresh a comment, archive it so we don't waste time on it.
			print("Could not 'refresh' comment: " + str(comment))
			requests.post(request_url + "/archive-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
			continue
		handeled = handle_comment(comment, sub_config.bot_username, sub, reddit, comment.id in new_ids, sub_config)
		time_made = comment.created
		# if this comment is more than a day old and we didn't find a correct looking reply
		if time.time() - time_made > 24 * 60 * 60 and not handeled:
			inform_comment_archived(comment, sub_config)
			requests.post(request_url + "/archive-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})

	# Check the archived comments at least 4 times a day.
	is_time_1 = is_time_between(datetime.time(2,0), datetime.time(2,9))
	is_time_2 = is_time_between(datetime.time(8,0), datetime.time(8,9))
	is_time_3 = is_time_between(datetime.time(14,0), datetime.time(14,9))
	is_time_4 = is_time_between(datetime.time(20,0), datetime.time(20,9))
	if is_time_1 or is_time_2 or is_time_3 or is_time_4 or debug:
		if debug:
			print("Looking through archived comments...")
		comments = []
		set_archived_comments(reddit, comments, sub_config)
		for comment in comments:
			try:
				comment.refresh()  # Don't know why this is required but it doesnt work without it so dont touch it
			except praw.exceptions.ClientException as e:
				print("Could not 'refresh' archived comment: " + str(comment)+ " with exception: \n    " + str(type(e).__name__) + " - " + str(e) + "\n    Removing comment...")
				requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
				continue
			except Exception as e:
				print("Could not 'refresh' archived comment: " + str(comment)+ " with exception: \n    " + str(type(e).__name__) + " - " + str(e))
				continue
			time_made = comment.created
			if time.time() - time_made > 7 * 24 * 60 * 60:  # if this comment is more than seven days old
				inform_comment_deleted(comment)
				requests.post(request_url + "/remove-comment/", {'sub_name': sub_config.subreddit_name, 'comment_id': comment.id, 'platform': PLATFORM})
			else:
				handle_comment(comment, sub_config.bot_username, sub, reddit, False, sub_config)
			time.sleep(.5)

	# This is for if anyone sends us a message requesting swap data
	for message in messages:
		if message.body[0:4] == "$add":
			handle_manual_adjustment(message, sub_config)
		else:
			handle_swap_data_request(message, sub_config)

if __name__ == "__main__":
	main()
