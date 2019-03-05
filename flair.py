import re
import json
import praw
import time
import datetime

debug = False

f = open("config.txt", "r")
info = f.read().splitlines()
f.close()

subreddit_name = info[0]
client_id = info[1]
client_secret = info[2]
bot_username = info[3]
bot_password = info[4]
FNAME_comments = 'database/active_comments-' + subreddit_name + '.txt'
FNAME_swaps = 'database/swaps-' + subreddit_name + ".json"
FNAME_archive = 'database/archive-' + subreddit_name + '.txt'

def update_flair(sub):
	flairs = sub.flair(limit=None)
	# Loop over each author and change their flair
	for flair in flairs:
		css = flair['flair_css_class']
		print(str(flair['user']) + " - " + css + " swaps")
		sub.flair.set(str(flair['user']).lower(), css+" swaps", css)


reddit = praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent='UserAgent', username=bot_username, password=bot_password)
sub = reddit.subreddit(subreddit_name)
update_flair(sub)
