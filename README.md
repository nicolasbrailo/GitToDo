# GitToDo
Github-backed ToDo list, with Telegram bot integration

This service will let you manage a ToDo list, backed by Git(hub), and with Telegram bot integration. With it, you can:

1. Keep a Markdown list of ToDo's, to change with any editor you'd like
2. In any device you'd like (since it's backed by git, just check it out in any computer)
3. With a Telegram bot integration (for those rare occasions when you're not near a computer!)

# Usage

Once the service is running (see the Installation section) you can use any text editor to change your ToDo file and commit it to Github as usual - no need to use this service. This service acts as a bridge to Telegram: if you are not near your computer, you can ask a Telegram bot to list, add or remove ToDos to your list.

* The Telegram bot command "/ls" will list all ToDos
* "/sections" will list all headings in the ToDo Markdown file
* "/ls $section" will list ToDos under a specific heading
* "/add $section text" will add ToDo text under $section. text is limited to a few 100's of characters.
* "/done <number>" will mark a ToDo as done, and remove it from the list

The command /ls will assign numbers to each ToDo, which you can then use with the /done command. Note these numbers are not stable (they will change after an /add or /done).

After every change to the ToDo list (/add and /done) the ToDo list will be checked in to Git and push to the origin repo, so that it may be sync'ed with other repos. Note that no smart merging is done - if a push or a pull fail, it must be resolved manually.


# Installation

To use this service:
1. Create a GitHub (private) repo.
2. Check it out wherever you plan to run this service. You should be able to push to the remote repo from the console (ie you should have an ssh key in GitHub for this computer)
3. Configure it! Make a copy of config.template.json into config.json, then
4. Goto Telegram BotFather (https://web.telegram.org/k/#@BotFather) and request a new bot. Copypaste the token you receive under "tok" in config.json.
5. Add a [list of] accepted chat IDs (alternatively, just wait until an error message saying "Unauthorized access from chat $ID", then add that ID)
6. Change the config key 'todo_filepath' to the full path of the file you'd like to use as a ToDo list. This file doesn't need to exist, but it's parent directory should exist and it should be the Git repo from step #1
7. Run this service with 'python3 ./main.py' (Or, altenratively, install as a system service with scripts/install_as_system_service.sh)


# Security

This service integrates with Telegram (and Git - quite likely Github):

* Telegram bot integration; the bot is built to only reply to a known set of commands, and ignore everything else. It also has a limit of tokens and words on each command. Additionally, only long-polling (instead of WebHooks are used)
* Unauthorized usage of the Telegram bot: The bot will only act on allow-listed chat ids, and a message from an Unauthorized user will trigger this service to kill itself.
* Github integration: If you use GitHub to back your ToDo file, it may be accesible (or visible) to other users, depending on the repo settings.

While the service should be relatively safe, storing sensitive information (eg passwords) is not recommended.


