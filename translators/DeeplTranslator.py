from translators.Translator import Translator
import deepl

class DeeplTranslator(Translator):
    def __init__(self, params):
        super(DeeplTranslator, self).__init__(params)

    def fix_lang(self, lang):
        overrides = self.params.get("lang_overrides")
        new_lang = None
        for override in overrides:
            if list(override.keys())[0] == lang:
                return list(override.values())[0]

        return lang



    def translate(self, text, lang, from_lang = None):
        translator = deepl.Translator(self.params.get("auth_key"))
        result = translator.translate_text(text, preserve_formatting=True, tag_handling='html', target_lang=self.fix_lang(lang), source_lang=self.fix_lang(from_lang))
        return result.text