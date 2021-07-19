If you would like to use this as a free of charge service, please fill out the following form. RegExr will be in touch shortly:

https://docs.google.com/forms/d/e/1FAIpQLSeonF2luQipQL29yL1j7jiE89XwypeBR3CW4mEJyzH0AjzzUg/viewform?usp=sf_link

## Features

* Users can tag the name of the bot and the name of the person they traded with in their trade thread to invoke the bot. When the tagged user replies to the comment with "confirmed" the bot will reply with "added" and give them credit.

* Users can send a message to the bot with u/<some_username> in the body of the message to get the feedback score for that person.

## Basic Run Instructions

* Clone this repository using `git clone`

* Create a config file in the config directory named `funkoswap-config.txt` with the following on seperate lines:

    * subreddit_name:<subreddit_name (no r/)>
    
    * client_id:<bot_client_id>
    
    * client_secret:<bot_client_secret>
    
    * bot_username:<bot_username (no u/)>
    
    * bot_password:<bot_password>
    
    * flair_word:<The default flair word>
    
    * mod_flair_word:<The Mod flair word (empty if no flair word)>

    * flair_templates:<Boolean (capital True or False)>

    * confirmation_text:<Optional text for the bot to say>

    * flair_threshold:<int>

    * mod_flair_template:<Reddit flair template ID>

    * titles:<Boolean (capital True or False)>

    * age_titles:<Boolean (capital True or False)>

    * black_list:<comma seperated list of reddit usernames, no spaces, no u/>

    * gets_flair_from:<comma seperated list of subreddit names, no spaces, no r/> (optionally, * for all subreddits, or * followed by a comma seperated list of subreddits to exclude)

    * discord_roles:<Boolean (capital True or False)>

    * discord_server_id:<int, optional>

* Add the relevant files in `age_titles/`, `roles/`, `templates/`, and 'titles/' if you elected to use them in the above configuration.

* Add the following cronjob using `crontab -e` 

    * `* * * * * cd ~/SwapBot && python runner.py <your_subreddit_name>-config.txt;`

    * `* * * * * cd ~/SwapBot && python server.py`

* If you want to keep local hourly backups of the database, run the following command:

    * `cd ~/SwapBot && mkdir backup`

* Then add the following lines to the crontab:

    * `0 * * * * cd ~/SwapBot && cp database/comments.json "backup/comments-"`date +"\%H"`".json"`

    * `0 * * * * cd ~/SwapBot && cp database/swaps.json "backup/swaps-"`date +"\%H"`".json"`
    
## Tools

* If you wish to increase someone's score on the back end, you can use `tools/add_batch_swap.py`. Please note that this does NOT change their flair.

* If you wish to add a comment ID that the bot missed for some reason, you can do so with `tools/add_comment.py

* If you wish to make an announcement to all of the subs in your config folder, you can edit the announcement text in `tools/announcement.py` and send it out by running that script

* If you wish to re-assign all flair to every user in your subreddit based on the database (if sub flair gets out of sync with the database, for any reason) you can do so with `tools/assign_all_flair.py`. Please note that this is a slow process, especially for subs with many members.

* If you wish to copy the swaps from one user to another (for example, if a user is switching to a new reddit account), you can do so with `tools/copy_user.py`. Please note that this does not update their flair.

* If you wish to remove a transaction from a user, you can do so with `tools/remove_swap.py`. Please note that this does not update their flair.

* If you wish to mark the last X number of tags and messages as unread in your bot account, you can do so with `tools/unread.py`

* If you wish to check if any of your bots are shadowbanned, modify `tools/shadow_ban_detector.py` to take in the name of your config file, then run the script.
