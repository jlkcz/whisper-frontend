#!/usr/bin/env python3

import os
import sys
import time
import sqlite3
import os.path
import datetime
import traceback
from pprint import pprint
from datetime import timedelta

import dotenv
dotenv.load_dotenv()
WHISPER_MODEL=os.environ.get("WHISPER_MODEL")
SLEEP_NOTASKS=os.environ.get("SLEEP_NOTASKS", 60)

import logging
logging.basicConfig(filename='instance/app.log', level=logging.DEBUG, format='[%(asctime)s] %(message)s')

import smtplib
from email.message import EmailMessage

import whisper
import yt_dlp

##### SQLite initialization ###

def adapt_datetime_iso(val):
    """Adapt datetime.datetime to timezone-naive ISO 8601 date."""
    return val.isoformat()

sqlite3.register_adapter(datetime.datetime, adapt_datetime_iso)

def convert_datetime(val):
    """Convert ISO 8601 datetime to datetime.datetime object."""
    return datetime.datetime.fromisoformat(val.decode())

sqlite3.register_converter("datetime", convert_datetime)

con = sqlite3.connect("instance/app.db", detect_types=sqlite3.PARSE_DECLTYPES)

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d
con.row_factory = dict_factory
cur = con.cursor()

### Sending emails ###

def send_task_over_email(to, subs, content, job_id, filename):
    server = os.environ.get("MAIL_SERVER", "localhost")
    port = os.environ.get("MAIL_PORT", 465)
    mail_user = os.environ.get("MAIL_USER")
    mail_pass = os.environ.get("MAIL_PASS")
    local_url = os.environ.get("LOCAL_URL")
    content = f"""Ahoj,

    tvůj přepis {job_id} souboru {filename} byl dokončen. Obsah si můžeš načíst jako titulky na {local_url}/result/{job_id} a jako čistý text na {local_url}/text/{job_id} Jako titulky ho najdeš i níže:

    Pac a pusu
    Tvůj Whisper!

    =============================
    {subs}
    ============================
    """
    msg = EmailMessage()
    msg.set_content(content)
    msg['Subject'] = f"[whisper] Přepis {job_id} hotov!"
    msg['From'] = mail_user
    msg['To'] = to


    with smtplib.SMTP_SSL(server, port) as smtp:
        smtp.login(mail_user, mail_pass)
        smtp.send_message(msg)
    return True

### Actual processing ###

logging.info("Starting process.py")
with con:
    while True:
        cur.execute("SELECT * FROM task WHERE done=0 AND started_at IS NULL ORDER BY created_at")
        unfinished_tasks = cur.fetchall()
        if not unfinished_tasks:
            logging.debug("No jobs to perform")
            time.sleep(SLEEP_NOTASKS)
            continue
        for row in unfinished_tasks:
            logging.info(f"Starting job {row['id']} ({row['file']})")
            cur.execute("UPDATE task SET started_at=? WHERE id=?", (datetime.datetime.now(), row["id"]))
            con.commit()
            #if it is URL, download first
            file = row["file"]
            if not row['file']:
                logging.info(f"Downloading {row['url']}")
                ydl = yt_dlp.YoutubeDL({
                      'quiet': True,
                      'verbose': False,
                      'format': 'bestaudio',
                      "outtmpl": os.path.join('instance','files', "%(id)s.%(ext)s"),
                      'postprocessors': [{'preferredcodec': 'mp3', 'preferredquality': '192', 'key': 'FFmpegExtractAudio', }],
                })
                try:
                    result = ydl.extract_info(row["url"], download=True)
                except Exception as e:
                    logging.error("Download of {row['url']} failed")
                    logging.error(traceback.format_exc())
                    continue
                file = f"{result['id']}.mp3"
                logging.debug(f"File saved as {file}")
                cur.execute("UPDATE task SET file=? WHERE id=?", (os.path.join('instance','files', f"{result['id']}.mp3"), row["id"]))
                con.commit()
            #now process
            model = whisper.load_model(WHISPER_MODEL)
            try:
                result = model.transcribe(os.path.join("instance","files",file), fp16=False)
            except Exception as e:
                logging.error("Transcribing {file} failed")
                logging.error(traceback.format_exc())
                continue
            subs = ""
            for segment in result["segments"]:
                startTime = str(0)+str(timedelta(seconds=int(segment['start'])))+',000'
                endTime = str(0)+str(timedelta(seconds=int(segment['end'])))+',000'
                text = segment['text']
                segmentId = segment['id']+1
                segment = f"{startTime} --> {endTime}\n{text[1:] if text[0] == ' ' else text}\n\n"
                subs += segment


            cur.execute("UPDATE task SET finished_at=?, result=?, subs=?, done=1 WHERE id=?", (datetime.datetime.now(), result["text"], subs, row["id"]))
            con.commit()
            logging.info(f"Job {row['id']} finished!")

            try:
                send_task_over_email(row['owner'], subs, result["text"], row["id"], file)
            except Exception as e:
                logging.error(f"Sending notification for job {row['id']} failed")
                logging.error(traceback.format_exc())
                continue
            logging.info(f"Notification for job {row['id']} sent!")
        time.sleep(30)
