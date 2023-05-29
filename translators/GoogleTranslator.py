from translators.Translator import Translator
from google.cloud import translate_v2 as translate

class GoogleTranslator(Translator):
    def __init__(self, params):
        super(GoogleTranslator, self).__init__(params)

    def translate(self, text, lang, from_lang = None):
        creds = get_credentials(oauth_file, GOOGLE_TRANSLATE_SCOPES)

        translate_client = translate.Client(credentials = creds)
        return translate_client.translate(text, target_language=lang)