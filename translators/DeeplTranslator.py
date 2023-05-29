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
        text_for_translate = text + "⠀" #hack with deepl. it may remove triangle brackets from the end, so add a U+2800 and then remove it rom result
        text_for_translate = text_for_translate.replace('<', '"<')
        text_for_translate = text_for_translate.replace('>', '>"')
        result = translator.translate_text(text_for_translate, target_lang=self.fix_lang(lang))
        result_text = result.text
        result_text = result_text.replace("⠀","")
        result_text = result_text.replace('"<', '<') #sometimes deepl translate tag name, add quotes before and remove after
        result_text = result_text.replace('>"', '>')
        return result_text