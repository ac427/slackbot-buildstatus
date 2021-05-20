#!/bin/env python3

"""slack bock which updates emoji of build status in pr links."""

from setup.db_operations import create_tables, insert_record
from GracefulKiller import GracefulKiller
import re
import os
import time
import threading
from github import Github
import slack
from slackeventsapi import SlackEventAdapter
from flask import Flask

# from setup.db_operations import create_database

APP = Flask(__name__)

GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
GITHUB_API = 'https://api.github.com'
SLACK_TOKEN = os.environ['SLACK_TOKEN']
SLACK_SIGNING_SECRET = os.environ['SLACK_SIGNING_SECRET']
SLACK_CLIENT = slack.WebClient(token=SLACK_TOKEN)

# Our app's Slack Event Adapter for receiving actions via the Events API
SLACK_EVENTS_ADAPTER = SlackEventAdapter(SLACK_SIGNING_SECRET, "/slack/events", APP)


# Get WebClient so you can communicate back to Slack.
# Where SLACK_API_TOKEN = SLACK_BOT_TOKEN
CLIENT = slack.WebClient(token=SLACK_TOKEN)

G = Github(base_url=GITHUB_API, login_or_token=GITHUB_TOKEN)

EMOJI = {"pass": "pass", "fail": "fail", "pending": "pending",
         "merge": "merge", "approved": "shipit", "open": "open",
         "change_requested": "change_requested"}

MONITORING_THREADS = {}


def github_ci_status(repo_name, pr_number):
    """Returns status of travis build. """
    sha = G.get_repo(repo_name).get_pull(pr_number).head.sha
    status = G.get_repo(repo_name).get_commit(sha).get_combined_status().state
    if status in ('failure', 'error'):
        value = EMOJI['fail']
    elif status == 'pending':
        value = EMOJI['pending']
    elif status == 'success':
        value = EMOJI['pass']
    return value

def github_status(repo_name, pr_number):
    """Returns pr status. """
    if G.get_repo(repo_name).get_pull(pr_number).is_merged():
        status = EMOJI['merge']
    else:
        status = None
        reviews = G.get_repo(repo_name).get_pull(pr_number).get_reviews()
        for review in range(0, len(list(reviews))):
            if reviews[review].state == 'APPROVED':
                status = EMOJI['approved']
            elif reviews[review].state == 'CHANGES_REQUESTED':
                status = EMOJI['change_requested']
    return [G.get_repo(repo_name).get_pull(pr_number).title, status]

def slack_post(channel, thread, message):
    """ Posts message in slack channel inside the thread. """
    CLIENT.chat_postMessage(
        channel=channel,
        thread_ts=thread,
        text=message)

def slack_react(channel, thread, emoji):
    """ Posts emoji inside slack channel thread. """
    try:
        CLIENT.reactions_add(channel=channel, timestamp=thread, name=emoji)
    except slack.errors.SlackApiError as error:
        if error.response['ok'] is False and error.response['error'] == 'already_reacted':
            pass

def slack_unreact(channel, thread, emoji):
    """ Remove emoji from slack channel inside the thread """
    try:
        CLIENT.reactions_remove(channel=channel, timestamp=thread, name=emoji)
    except slack.errors.SlackApiError as error:
        if error.response['ok'] is False and error.response['error'] == 'already_reacted':
            pass

def monitor_list(meta):
    """Keep list of umerged threads to check periodically. """
    MONITORING_THREADS[meta[0]] = meta[1:]


@SLACK_EVENTS_ADAPTER.on("message")
def handle_message(event_data):
    """" Reads incoming message and looks if it is git pull request. """
    message = event_data["event"]
    text = message.get("text")
    if text:
        git_url = re.findall(r'https://github.com/\S+/\S+/pull/\d+', text)
    # going to take only the first url in message and ignore rest
    if git_url:
        first_url = git_url[0].split('/')
        print(first_url)
        channel_id = message["channel"]
        thread_ts = message['ts']
        url_meta = {"repo_name": first_url[3] + "/" + first_url[4],
                    "pull_number": int(first_url[6])}
        git_status = github_status(
            url_meta["repo_name"],
            url_meta["pull_number"])
        #git_title = 'Github issue title: ' + \
        #    github_status(url_meta["repo_name"], url_meta["pull_number"])[0]
        ci_status = github_ci_status(url_meta["repo_name"], url_meta["pull_number"])
        reaction_list = CLIENT.reactions_get(
            channel=channel_id, timestamp=thread_ts, full="true")

        updated_emoji_list = []
        if ci_status:
            updated_emoji_list.append(ci_status)
        if 'reply_count' not in reaction_list['message']:
            slack_post(channel_id, thread_ts, git_status[0])
        if git_status[1] == 'merge':
            updated_emoji_list.append(git_status[1])
        else:
            updated_emoji_list.append(git_status[1])
            insert_record(thread_ts, url_meta["repo_name"], url_meta["pull_number"], channel_id, ci_status)

            monitor_list([thread_ts, url_meta["repo_name"], \
            url_meta["pull_number"], channel_id, ci_status])

        for item in updated_emoji_list:
            slack_react(channel_id, thread_ts, item)

# Error events
@SLACK_EVENTS_ADAPTER.on("error")
def error_handler(err):
    """ Prints errors to stdout. """
    print("ERROR: " + str(err))

global killer

@APP.before_first_request
def activate_job():
    """ Monitor all the unmerged jobs """
    create_tables()

    def run_job():
        while not killer.kill_now:
            del_threads = []
            if MONITORING_THREADS:
                print("MONITORING_THREADS are ")
                print(MONITORING_THREADS)
                for key, value in MONITORING_THREADS.items():
                    monitor_ci_status = github_ci_status(value[0], value[1])
                    monitor_channel_id = value[2]
                    monitor_thread_ts = key
                    if monitor_ci_status != value[3]:
                        slack_unreact(monitor_channel_id, monitor_thread_ts, value[3])
                        slack_react(monitor_channel_id, monitor_thread_ts, monitor_ci_status)
                        MONITORING_THREADS[key] = [value[0], value[1],\
                        value[2], monitor_ci_status]
                    if G.get_repo(value[0]).get_pull(value[1]).is_merged():
                        slack_react(monitor_channel_id, monitor_thread_ts, 'merge')
                        del_threads.append(key)
            for item in del_threads:
                del MONITORING_THREADS[item]
            time.sleep(30)
    thread = threading.Thread(target=run_job)
    thread.start()

if __name__ == "__main__":
    killer = GracefulKiller()

    APP.run(port=5000)
