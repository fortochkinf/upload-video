from translators.Translator import Translator
import deepl

class DeeplTranslator(Translator):
    def __init__(self, params):
        super(DeeplTranslator, self).__init__(params)

    def translate(self, text, lang, from_lang = None):
        translator = deepl.Translator(self.params.get("auth_key"))
        result = translator.translate_text(text, target_lang=lang)
        return result.text