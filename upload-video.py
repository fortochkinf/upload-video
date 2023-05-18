#!/home/aparfenov/projects/upload-video/venv/bin/python

import http.client
import httplib2
import os
import random
import sys
import time
import yaml


import datetime

import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

# Explicitly tell the underlying HTTP transport library not to retry, since
# we are handling retry logic ourselves.
httplib2.RETRIES = 1

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError, http.client.NotConnected,
                        http.client.IncompleteRead, http.client.ImproperConnectionState,
                        http.client.CannotSendRequest, http.client.CannotSendHeader,
                        http.client.ResponseNotReady, http.client.BadStatusLine)

# Always retry when an apiclient.errors.HttpError with one of these status
# codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

CONFIGURATION_FILE = "settings.yaml"

CLIENT_SECRETS_FILE = 'client_secret.json'
TOKEN_CACHE_FILE = 'token.json'

# This OAuth 2.0 access scope allows an application to upload files to the
# authenticated user's YouTube channel, but doesn't allow other types of access.
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")

VIDEO_FILE_EXTENSION = ("mov", "mpeg", "mpg", "mp4", "avi", "wmv", "flv", "3gp")
VIDEO_THUMBNAIL_EXTENSION = ("jpg", "jpeg", "gif", "png")

PLACEHOLDER="<PHRASE_FROM_FILE>"
VIDEO_NAME_PLACEHOLDER="<VIDEO_NAME>"

# Authorize the request and store authorization credentials.
def get_authenticated_service():
  creds = None
  if os.path.exists(TOKEN_CACHE_FILE):
    creds = Credentials.from_authorized_user_file(TOKEN_CACHE_FILE, SCOPES)
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
      creds = flow.run_local_server(port=0)
  with open(TOKEN_CACHE_FILE, 'w') as token:
    token.write(creds.to_json())
  return build(API_SERVICE_NAME, API_VERSION, credentials = creds)

def initialize_upload(youtube, options):
  body=dict(
    snippet=dict(
      title=options.get("name"),
      description=options.get("description"),
    ),
    status=dict(
      privacyStatus=options.get("privacy"),
      selfDeclaredMadeForKids=False,
      publishAt=options.get("publish_time")
    )
  )
  print(body)
  # Call the API's videos.insert method to create and upload the video.
  insert_request = youtube.videos().insert(
      part=",".join(body.keys()),
      body=body,
      # The chunksize parameter specifies the size of each chunk of data, in
      # bytes, that will be uploaded at a time. Set a higher value for
      # reliable connections as fewer chunks lead to faster uploads. Set a lower
      # value for better recovery on less reliable connections.
      #
      # Setting "chunksize" equal to -1 in the code below means that the entire
      # file will be uploaded in a single HTTP request. (If the upload fails,
      # it will still be retried where it left off.) This is usually a best
      # practice, but if you're using Python older than 2.6 or if you're
      # running on App Engine, you should set the chunksize to something like
      # 1024 * 1024 (1 megabyte).
      media_body=MediaFileUpload(options.get("file"), chunksize=-1, resumable=True)
  )

  return resumable_upload(insert_request)


def resumable_upload(insert_request):
  response = None
  error = None
  retry = 0
  while response is None:
    try:
      print("Uploading file...")
      status, response = insert_request.next_chunk()
      if response is not None:
        if 'id' in response:
          print("Video id '%s' was successfully uploaded." % response['id'])
          return response['id']
        else:
          exit("The upload failed with an unexpected response: %s" % response)
    except HttpError:
      if e.resp.status in RETRIABLE_STATUS_CODES:
        error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status,
                                                             e.content)
      else:
        raise
    except RETRIABLE_EXCEPTIONS:
      error = "A retriable error occurred: %s" % e

    if error is not None:
      print(error)
      retry += 1
      if retry > MAX_RETRIES:
        exit("No longer attempting to retry.")

      max_sleep = 2 ** retry
      sleep_seconds = random.random() * max_sleep
      print("Sleeping %f seconds and then retrying..." % sleep_seconds)
      time.sleep(sleep_seconds)

def replace_placeholders(filename, str, video_name=None):
  with open(filename, 'r') as file:
      lines = file.readlines()

  placeholders_count = str.count(PLACEHOLDER)
  if placeholders_count > len(lines):
      placeholders_count = len(lines)
  random_strings = random.sample(lines, placeholders_count)
  output_string = str

  for random_string in random_strings:
    output_string = output_string.replace(PLACEHOLDER, random_string.strip(), 1)

  output_string = output_string.replace(PLACEHOLDER, "")

  if (video_name != None):
      output_string = output_string.replace(VIDEO_NAME_PLACEHOLDER, video_name)

  return output_string

def read_config():
    return  yaml.safe_load(Path(CONFIGURATION_FILE).read_text())

def get_placeholders_filename(dir, video_file):
    return os.path.splitext(os.path.join(dir,video_file))[0]+'.txt'

def calculate_publish_time(days_after, at_time):
    hour = int(at_time.split(":")[0])
    minute = int(at_time.split(":")[1])
    date = datetime.datetime.now()
    date = date + datetime.timedelta(days=days_after)
    date.replace(hour=hour, minute=minute)

    #YYYY-MM-DDThh:mm:ss.sZ
    return date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

def upload_thumbnail(youtube, video_id, file):
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=file
    ).execute()

def get_thumnail_file(dir, video_file):
    for file in sorted(os.listdir(dir)):
        if file.endswith(VIDEO_THUMBNAIL_EXTENSION) and file.startswith(os.path.splitext(video_file)[0]):
            return os.path.join(dir,file)


if __name__ == '__main__':
  config = read_config()
  youtube = get_authenticated_service()

  video_upload_props = {}

  for channel in config.get("channels"):
    video_dir = channel.get("publish_directory")
    archive_dir = channel.get("archive_directory")
    for video_file in sorted(os.listdir(video_dir)):
        if video_file.endswith(VIDEO_FILE_EXTENSION):
            print(video_file)

            channel_type = {}
            for a in config.get("channel_types"):
                if a.get("id") == channel.get("type"):
                    channel_type = a

            video_name = random.choice(channel_type.get("video_name_variants"))
            video_description = random.choice(channel_type.get("video_description_variants"))

            placeholders_filename = get_placeholders_filename(video_dir, video_file)

            video_upload_props["name"] = replace_placeholders(placeholders_filename, video_name)
            video_upload_props["description"] = replace_placeholders(placeholders_filename, video_description, os.path.splitext(video_file)[0])
            video_upload_props["privacy"] = channel.get("publication_options").get("privacy")
            video_upload_props["file"] = os.path.join(video_dir,video_file)

            publish_time = calculate_publish_time(
                channel.get("publication_options").get("schedule").get("days_after"),
                channel.get("publication_options").get("schedule").get("at_time")
            )

            video_upload_props["publish_time"] = publish_time

            try:
              video_id = initialize_upload(youtube, video_upload_props)
              upload_thumbnail(youtube, video_id, get_thumnail_file(video_dir, video_file))
            except HttpError:
              print("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))
