from translators.Translator import Translator

from authorization.Authorization import *
from google.cloud import translate_v2 as translate

class GoogleTranslator(Translator):



    def __init__(self, params):
        super(GoogleTranslator, self).__init__(params)

    def translate(self, text, lang, from_lang = None):
        oauth_file = os.path.join("secrets",self.params.get("oauth_secret_file"))
        GOOGLE_TRANSLATE_SCOPES = ['https://www.googleapis.com/auth/cloud-translation']

        creds = get_credentials(oauth_file, GOOGLE_TRANSLATE_SCOPES)

        translate_client = translate.Client(credentials=creds)
        translated_text = translate_client.translate(text, format_='text', target_language=lang, source_language=from_lang)
        return translated_text.get("translatedText")
