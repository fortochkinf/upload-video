#!/usr/bin/python

import http.client
import httplib2
import os
import random
import time
import yaml
import google.cloud
import datetime

import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow


from translators.Translator import Translator
from translators.DeeplTranslator import DeeplTranslator
from translators.GoogleTranslator import GoogleTranslator


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

# This OAuth 2.0 access scope allows an application to upload files to the
# authenticated user's YouTube channel, but doesn't allow other types of access.
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
GOOGLE_TRANSLATE_SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")

VIDEO_FILE_EXTENSION = ("mov", "mpeg", "mpg", "mp4", "avi", "wmv", "flv", "3gp")
VIDEO_THUMBNAIL_EXTENSION = ("jpg", "jpeg", "gif", "png")

PLACEHOLDER="<PHRASE_FROM_FILE>"
VIDEO_NAME_PLACEHOLDER="<VIDEO_NAME>"



def get_credentials(oauth_file, scopes):
    creds = None
    token_cache_file_name = oauth_file + ".cache"
    if os.path.exists(token_cache_file_name):
        creds = Credentials.from_authorized_user_file(token_cache_file_name, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(oauth_file, scopes)
            creds = flow.run_local_server(port=0)
    with open(token_cache_file_name, 'w') as token:
        token.write(creds.to_json())
    return creds

# Authorize the request and store authorization credentials.
def get_authenticated_service_oauth(oauth_file):
    creds = get_credentials(oauth_file, YOUTUBE_SCOPES)
    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials = creds)

def get_authenticated_service_api_key(key):
  return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=key)

def translate_video_description(title, description, placeholders_filename, langs, transaltor):
    localization = {}
    for lang in langs:
        values = {}
        values['title'] = replace_placeholders(filename=placeholders_filename, str=title, translator=transaltor, lang=lang)
        values['description'] = replace_placeholders(filename=placeholders_filename, str=description, video_name=values['title'], translator=transaltor, lang=lang)
        localization[lang] = values
    return localization

def initialize_upload(youtube, options):
  body=dict(
    snippet=dict(
      title=options.get("name"),
      description=options.get("description"),
      defaultLanguage="ru"
    ),
    status=dict(
      privacyStatus=options.get("privacy"),
      selfDeclaredMadeForKids=False,
    ),
      localizations=options.get("localization")
  )
  if options.get("publish_time") is not None:
      body.get("status")["publishAt"] = options.get("publish_time")

  print("Youtube video upload request:\n" + str(body))
  # Call the API's videos.insert method to create and upload the video.
  insert_request = youtube.videos().insert(
      part=",".join(body.keys()),
      body=body,
      media_body=MediaFileUpload(options.get("file"), chunksize=-1, resumable=True)
  )

  return "123"
  #return resumable_upload(insert_request)


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

def replace_placeholders(filename, str, video_name=None, translator=None, lang=None):
  with open(filename, 'r') as file:
      lines = file.readlines()

  replacement_count = min(str.count(PLACEHOLDER), len(lines))
  random_strings = random.sample(lines, replacement_count)
  output_string = str

  if translator is not None and lang is not None:
      output_string = translator.translate(output_string, lang)
      print("output_string = " + output_string)

  for random_string in random_strings:
    if translator is not None and lang is not None:
      random_string = translator.translate(random_string, lang)
      print("random_string = " + random_string)
    replaced_string = output_string.replace("#" + PLACEHOLDER, "#" + random_string.strip().replace(" ", ""), 1)
    if replaced_string == output_string:
      output_string = output_string.replace(PLACEHOLDER, random_string.strip(), 1)
    else:
      output_string = replaced_string
  output_string = output_string.replace("#" + PLACEHOLDER, "")
  output_string = output_string.replace(PLACEHOLDER, "")

  if video_name is not None:
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
    date = date.replace(hour=hour, minute=minute, second=0)
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


def generate_upload_props(channel, config, video_file):

    channel_type = None
    for channel_type_candidate in config.get("channel_types"):
        if channel_type_candidate.get("id") == channel.get("type"):
            channel_type = channel_type_candidate

    if channel_type is None:
        raise Exception("Cant find channel type: " + channel_type)

    video_dir = channel.get("publish_directory")

    translator = get_translator(channel, config.get("translators"))
    language_list = channel.get("translation").get("languages")
    video_upload_props = {}
    video_name = random.choice(channel_type.get("video_name_variants"))
    video_description = random.choice(channel_type.get("video_description_variants"))

    placeholders_filename = get_placeholders_filename(video_dir, video_file)

    if os.path.exists(placeholders_filename):
        video_upload_props["name"] = replace_placeholders(filename=placeholders_filename, str=video_name)
        video_upload_props["description"] = replace_placeholders(filename=placeholders_filename, str=video_description, video_name=video_upload_props["name"])
    else:
        video_upload_props["name"] = video_name
        video_upload_props["description"] = video_description
        print("WARN! Placeholders file: " + placeholders_filename + " not exists. Using file name as video name.")


    video_upload_props["localization"] = translate_video_description(video_name, video_description, placeholders_filename,  language_list, translator)

    video_upload_props["privacy"] = channel.get("publication_options").get("privacy")
    video_upload_props["file"] = os.path.join(video_dir,video_file)
    publication_options = channel.get("publication_options")
    if publication_options.get("schedule") is not None:
        schedule = publication_options.get("schedule")
        try:
            publish_time = calculate_publish_time(schedule.get("days_after"),schedule.get("at_time")[video_num])
        except IndexError:
            print("Schedule have only " + video_num + " records in total, but there are more videos for upload, so skipping upload next videos")
            exit(1)
        video_upload_props["publish_time"] = publish_time
    else:
        print("INFO: publication schedule is not set")
    return  video_upload_props



def get_translator(channel, transaltors) -> Translator:
    if channel.get("translation") is not None:
        if channel.get("translation").get("enabled") is True:

            translator_name = channel.get("translation").get("translator")
            translator = None
            for translator_candidate in transaltors:
                if (translator_candidate.get("name") == translator_name):
                    translator = translator_candidate
            if (translator is None):
                raise Exception("Translator not found by name: " + translator_name)

            properties = translator.get("properties")
            translator_type = translator.get("type")
            if (translator_type == "google"):
                return GoogleTranslator(properties)
            elif (translator_type == "deepl"):
                return DeeplTranslator(properties)
            else:
                raise Exception("Unknown translator type: " + translator_type)
    return None

if __name__ == '__main__':
  config = read_config()


  video_upload_props = {}

  for channel in config.get("channels"):
    print("Channel: " + channel.get("name"))
    video_dir = channel.get("publish_directory")
    archive_dir = channel.get("archive_directory")
    credential_file_path = os.path.join("secrets",channel.get("oauth_secret_file"))
    youtube = get_authenticated_service_oauth(os.path.join("secrets",channel.get("oauth_secret_file")))
    video_num = 0
    for video_file in sorted(os.listdir(video_dir)):
        if video_file.endswith(VIDEO_FILE_EXTENSION):
            print("Uploading video: "+ video_file)

            video_upload_props = generate_upload_props(channel, config, video_file)
            video_num = video_num + 1
            try:
              video_id = initialize_upload(youtube, video_upload_props)
              thumbnail_file = get_thumnail_file(video_dir, video_file)
              if os.path.exists(thumbnail_file):
                print("Setting thumbnail " + thumbnail_file + " for video id: " + video_id)
                #upload_thumbnail(youtube, video_id, thumbnail_file)
              else:
                print("WARN! Thumbnail file not exists: " + thumbnail_file)
              os.rename(thumbnail_file, os.path.join(archive_dir, os.path.basename(thumbnail_file)))
              os.rename(os.path.join(video_dir, video_file), os.path.join(archive_dir, video_file))
              os.rename(
                get_placeholders_filename(video_dir, video_file),
                os.path.join(archive_dir, os.path.basename(get_placeholders_filename(video_dir, video_file)))
              )
            except HttpError:
              print("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))
