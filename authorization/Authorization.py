import os

import google.cloud
import google.oauth2.credentials
from googleapiclient.discovery import build

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials


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
def get_authenticated_service_oauth(oauth_file, scopes, service, api_version):
    creds = get_credentials(oauth_file, scopes)
    return build(service, api_version, credentials = creds)
