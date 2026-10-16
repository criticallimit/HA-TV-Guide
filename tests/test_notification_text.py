"""TV Guide keeps its reminder language templates."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('tv_guide_notification_text',Path(__file__).resolve().parents[1]/'custom_components'/'tv_guide'/'notification_text.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class NotificationTextTests(unittest.TestCase):
    def test_german_and_english_original_messages(self):
        item={'channel':'ZDF','title':'Film','language':'de'}
        self.assertIn('beginnt um 20:15',module.reminder_text(item,'20:15')['message'])
        item['language']='en'
        self.assertIn('20:15',module.reminder_text(item,'20:15')['message'])
        self.assertNotIn('beginnt um',module.reminder_text(item,'20:15')['message'])

    def test_auto_language_normalizes_installation_locale_like_explicit_language(self):
        for locale in ['de_DE','DE-de','nb_NO','no_NO','fr_FR']:
            with self.subTest(locale=locale):
                item={'channel':'Station','title':'Film'}
                explicit=module.reminder_text({**item,'language':locale},'20:15')
                automatic=module.reminder_text({**item,'language':'auto'},'20:15',locale)
                self.assertEqual(automatic,explicit)

    def test_all_original_languages_have_translations(self):
        for language in ['de','en','nl','fr','it','da','nb','sv']:
            result=module.reminder_text({'channel':'TV','title':'Programme','language':language},'18:00')
            self.assertIn('Programme',result['message'])
            self.assertIn('18:00',result['message'])


if __name__=='__main__':unittest.main()
