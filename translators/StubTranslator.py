from translators.Translator import Translator


class StubTranslator(Translator):
    def __init__(self, params):
        super(StubTranslator, self).__init__(params)


    def translate(self, text, lang, from_lang = None):
        return text