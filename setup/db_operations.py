import sqlite3

DB_NAME = 'slack_bot_database.db'

def db_connect():
    con = sqlite3.connect(DB_NAME, check_same_thread=False)

    return con

con = db_connect()

def create_tables():
    create_status_table_query =  """ CREATE TABLE IF NOT EXISTS status (
                                        id integer PRIMARY KEY,
                                        thread_ts integer,
                                        repo_name text NOT NULL,
                                        pull_number integer,
                                        channel_name text,
                                        state text
                                    ); """

    c = con.cursor()
    c.execute(create_status_table_query)

def insert_record(thread_ts, repo_name, pull_number, channel_name, state):
    insert_query = "INSERT INTO status(thread_ts, repo_name, pull_number, channel_name, state) VALUES(?, ?, ?, ?, ?)"

    c = con.cursor()
    c.execute(insert_query, (thread_ts, repo_name, pull_number, channel_name, state))


