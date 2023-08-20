#!/usr/bin/python

import http.client
import httplib2
import os
import random
import time
import yaml
import google.cloud
import datetime
import re
import pytz
import argparse


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
from translators.StubTranslator import StubTranslator
from exceptions.ScheduleNotPresentException import ScheduleNotPresentException
from exceptions.QuotaExceededException import QuotaExceededException


from authorization.Authorization import *


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


VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")

VIDEO_FILE_EXTENSION = ("mov", "mpeg", "mpg", "mp4", "avi", "wmv", "flv", "3gp")
VIDEO_THUMBNAIL_EXTENSION = ("jpg", "jpeg", "gif", "png")

PLACEHOLDER="<PHRASE_FROM_FILE>"
VIDEO_NAME_PLACEHOLDER="<VIDEO_NAME>"


config = yaml.safe_load(Path(CONFIGURATION_FILE).read_text())

def translate_video_description(title, description, placeholders_filename, langs, transaltor, source_lang):
    localization = {}
    for lang in langs:
        values = {}
        values['title'] = truncate_by_length_at_last_character(replace_placeholders(
            filename=placeholders_filename, text=title, translator=transaltor, lang=lang, from_lang=source_lang), config.get("title_max_length"), " ")
        values['description'] = truncate_by_length_at_last_character(replace_placeholders(
            filename=placeholders_filename, text=description, video_name=values['title'], translator=transaltor, lang=lang, from_lang=source_lang), config.get("description_max_length"), " ")
        localization[lang] = values
    return localization

def initialize_upload(youtube, options):
  body=dict(
    snippet=dict(
      title=options.get("name"),
      description=options.get("description"),
      defaultLanguage=options.get("default_language"),
      defaultAudioLanguage=options.get("default_language"),
      tags=options.get("tags")
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
    except HttpError as e:
      if e.resp.status in RETRIABLE_STATUS_CODES:
        error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status, e.content)
      else:
        if e.content.find(b"quotaExceeded") != -1:
            raise QuotaExceededException
        raise
    except RETRIABLE_EXCEPTIONS as e:
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


def is_translation_meaningless(text):
    allowed_s = "!@#$%^&*()_-+=\"'|\?/.,:[]<>";
    return all(ch in allowed_s for ch in text)

def truncate_by_length_at_last_character(text, max_size, char):
    if len(text) <= max_size:
        return text
    print("WARNING!!!: ", "Text length ", len(text) ," is out of limit! Text:\n" + text)
    print("truncated to:\n",text[0:text.rindex(char, 0, max_size)])
    return text[0:text.rindex(char, 0, max_size)]

def replace_placeholders(filename, text, video_name=None, translator=None, lang=None, from_lang=None):

  try:
      with open(filename, 'r') as file:
          lines = file.readlines()
  except FileNotFoundError:
      lines = []

  replacement_count = min(text.count(PLACEHOLDER), len(lines))
  random_strings = random.sample(lines, replacement_count)
  string_parts = re.split('(#*<.+?>|\\n)',text)

  #print(random_strings)
  random_string_num = 0

  for i in range(len(string_parts)):
      part = string_parts[i]

      if part.strip() == "" or part == "\n":
          string_parts[i] = part
          continue

      try:
          if len(random_strings) > 0:
            random_string = random_strings[random_string_num].strip()
          else:
            random_string = ""
            string_parts[i] = ""
      except IndexError:
          string_parts[i] = ""
          continue

      leading_spaces = len(part) - len(part.lstrip())
      trailing_spaces = len(part) - len(part.rstrip())

      part = part.strip()
      #print("part: ", part, ", leading: ", leading_spaces, ", trailing: ", trailing_spaces)
      hashtag = False

      if part == ('#' + PLACEHOLDER):
          replacement = random_string
          random_string_num = random_string_num + 1
          hashtag = True
      elif part == PLACEHOLDER:
          replacement = random_string
          random_string_num = random_string_num + 1

      elif part == VIDEO_NAME_PLACEHOLDER:
          replacement = video_name

      else:
          replacement = part

      if translator is not None and lang is not None and replacement != "":
          before_translate = replacement
          if not is_translation_meaningless(replacement):
            replacement = truncate_by_length_at_last_character(replacement,config.get("description_max_length")," ")
            replacement = translator.translate(replacement, lang, from_lang).strip()
            print("Translator call. text:", before_translate, "translated:", replacement, "lang:", lang, "from_lang:", from_lang)


      if hashtag:
          replacement = '#' + ''.join(ch for ch in replacement if ch.isalnum()).lower()

      replacement = (' ' * leading_spaces) + replacement + (' ' * trailing_spaces)

      string_parts[i] = replacement
      #print("replacement: ", replacement, ", leading: ", leading_spaces, ", trailing: ", trailing_spaces)


  result = ''.join(string_parts).rstrip()
  #print("result: ", result)

  return result

def get_placeholders_filename(dir, video_file):
    return os.path.splitext(os.path.join(dir,video_file))[0]+'.txt'

def calculate_publish_time(days_after, at_time):
    hour = int(at_time.split(":")[0])
    minute = int(at_time.split(":")[1])
    date = datetime.datetime.now(pytz.timezone(config.get("timezone")))
    date = date + datetime.timedelta(days=days_after)
    date = date.replace(hour=hour, minute=minute, second=0)
    date = date - (date.replace(tzinfo=datetime.timezone.utc) - date.astimezone(datetime.timezone.utc))

    #YYYY-MM-DDThh:mm:ss.sZ
    return date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

def upload_thumbnail(youtube, video_id, file):
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=file
    ).execute()

def get_thumbnail_file(dir, video_file):
    for file in sorted(os.listdir(dir)):
        if file.endswith(VIDEO_THUMBNAIL_EXTENSION) and file.startswith(os.path.splitext(video_file)[0]):
            return os.path.join(dir,file)


def get_tags(filename, tags_list):
    print("tagsList", tags_list)
    if tags_list is not None:
        result = []
        try:
            with open(filename, 'r') as file:
                lines = file.readlines()
        except FileNotFoundError:
            lines = []

        placeholder_count = 0
        for tag in tags_list:
            if tag.strip() == PLACEHOLDER:
                placeholder_count = placeholder_count + 1

        replacement_count = min(placeholder_count, len(lines))
        random_strings = random.sample(lines, replacement_count)

        tag_number = 0
        for tag in tags_list:
            if tag.strip() == PLACEHOLDER:
                if (tag_number <= replacement_count):
                    result.append(random_strings[tag_number].strip())
            else:
                result.append(tag)

        return result

    else:
        return None

def generate_upload_props(channel, video_file, video_num):

    video_upload_props = {}
    publication_options = channel.get("publication_options")
    if publication_options.get("schedule") is not None:
        schedule = publication_options.get("schedule")
        try:
            publish_time = calculate_publish_time(schedule[video_num].get("days_after"),schedule[video_num].get("at_time"))
        except IndexError:
            print("Schedule have only " + str(video_num) + " records, but there are more videos for upload, so skipping upload next videos")
            raise ScheduleNotPresentException
        video_upload_props["publish_time"] = publish_time
    else:
        print("INFO: publication schedule is not set")


    channel_type = None
    for channel_type_candidate in config.get("channel_types"):
        if channel_type_candidate.get("id") == channel.get("type"):
            channel_type = channel_type_candidate

    if channel_type is None:
        raise Exception("Cant find channel type: " + channel_type)

    video_dir = channel.get("publish_directory")

    translator = get_translator(channel, config.get("translators"))
    language_list = channel.get("translation").get("languages")

    video_name = random.choice(channel_type.get("video_name_variants"))
    video_description = random.choice(channel_type.get("video_description_variants"))

    placeholders_filename = get_placeholders_filename(video_dir, video_file)

    video_upload_props["name"] = truncate_by_length_at_last_character(replace_placeholders(filename=placeholders_filename, text=video_name), config.get("title_max_length"), " ")
    video_upload_props["description"] = truncate_by_length_at_last_character(replace_placeholders(filename=placeholders_filename, text=video_description, video_name=video_upload_props["name"]), config.get("description_max_length"), " ")

    video_upload_props["localization"] = translate_video_description(video_name, video_description, placeholders_filename,  language_list, translator, channel.get("default_language"))

    video_upload_props["privacy"] = channel.get("publication_options").get("privacy")
    video_upload_props["file"] = os.path.join(video_dir,video_file)
    print("channel_type", channel_type)
    video_upload_props["tags"] = get_tags(placeholders_filename, channel_type.get("video_tags_variants"))

    video_upload_props["default_language"] = channel.get("default_language")
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
            elif (translator_type == "stub"):
                return StubTranslator(properties)
            else:
                raise Exception("Unknown translator type: " + translator_type)
    return None

if __name__ == '__main__':

  parser = argparse.ArgumentParser()
  parser.add_argument('--channel', dest='channel', type=str, help='specific channel')
  args = parser.parse_args()

  video_upload_props = {}

  for channel in config.get("channels"):
    if args.channel is not None and str(channel.get("id")) != args.channel:
        continue
    print("Channel: " + channel.get("name"))
    video_dir = channel.get("publish_directory")
    archive_dir = channel.get("archive_directory")
    credential_file_path = os.path.join("secrets",channel.get("oauth_secret_file"))
    youtube = get_authenticated_service_oauth(os.path.join("secrets",channel.get("oauth_secret_file")), YOUTUBE_SCOPES, YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION)
    video_num = 0
    try:
        for video_file in sorted(os.listdir(video_dir)):
            if video_file.endswith(VIDEO_FILE_EXTENSION):
                print("Uploading video: "+ video_file)
                video_upload_props = generate_upload_props(channel, video_file, video_num)
                video_num = video_num + 1
                try:
                  video_id = initialize_upload(youtube, video_upload_props)
                  thumbnail_file = get_thumbnail_file(video_dir, video_file)
                  if os.path.exists(thumbnail_file):
                    print("Setting thumbnail " + thumbnail_file + " for video id: " + video_id)
                    upload_thumbnail(youtube, video_id, thumbnail_file)
                  else:
                    print("WARN! Thumbnail file not exists: " + thumbnail_file)
                  try:
                    os.rename(thumbnail_file, os.path.join(archive_dir, os.path.basename(thumbnail_file)))
                  except FileNotFoundError:
                    pass
                  try:
                    os.rename(os.path.join(video_dir, video_file), os.path.join(archive_dir, video_file))
                  except FileNotFoundError:
                    pass
                  try:
                      os.rename(
                        get_placeholders_filename(video_dir, video_file),
                        os.path.join(archive_dir, os.path.basename(get_placeholders_filename(video_dir, video_file)))
                      )
                  except FileNotFoundError:
                    pass
                except HttpError as e:
                  print("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))
    except (ScheduleNotPresentException, QuotaExceededException) as e:
        if e.__class__.__name__ == "QuotaExceededException":
           print("ERROR!!! Quota exceeded skipping this channel.")
        continue
