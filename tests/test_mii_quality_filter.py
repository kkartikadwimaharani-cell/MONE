import unittest

import mii_quality_filter as quality_filter


class MiiQualityFilterTests(unittest.TestCase):
    def build(self, prompt, **kwargs):
        return quality_filter.build_final_prompt(prompt, **kwargs)

    def test_deterministic_output_and_exact_repetition_cleanup(self):
        prompt = "A woman opens the door. A woman opens the door. Then she smiles."
        first = self.build(prompt, family="seedance", duration=8)
        self.assertEqual(first, self.build(prompt, family="seedance", duration=8))
        self.assertEqual(first.count("A woman opens the door."), 1)

    def test_english_scene_gets_performance_and_progression(self):
        final = self.build("A woman walks inside, opens a letter, then looks at her friend and smiles.",
                           family="seedance25", duration=15)
        self.assertIn("chronological order", final)
        self.assertIn("micro-expression", final)
        self.assertIn("screen direction", final)

    def test_indonesian_scene_is_understood(self):
        final = self.build("Seorang wanita berjalan ke meja, lalu duduk, membuka surat, dan tersenyum.",
                           family="seedance25", duration=12)
        self.assertIn("chronological order", final)
        self.assertIn("body weight", final)
        self.assertIn("CHARACTER:", final)

    def test_mixed_english_indonesian_scene(self):
        final = self.build("A man berdiri by the window, kemudian menoleh and walks keluar.",
                           family="seedance25", duration=16)
        self.assertIn("chronological order", final)
        self.assertIn("entrances, exits", final)

    def test_explicit_camera_lighting_and_grade_win(self):
        prompt = "Locked camera close-up. A woman speaks under hard red lighting with monochrome grading."
        final = self.build(prompt, family="wan30", duration=7)
        self.assertIn("Locked camera close-up", final)
        self.assertNotIn("natural reframing", final)
        self.assertNotIn("motivated environmental light", final)
        self.assertNotIn("natural cinematic grade", final)

    def test_valid_sequential_camera_changes_are_preserved(self):
        prompt = "Locked opening shot, then a tracking shot follows the man into the room."
        final = self.build(prompt, family="seedance25", duration=10)
        self.assertIn(prompt, final)
        self.assertIn("Locked opening shot", final)
        self.assertIn("tracking shot", final)

    def test_reference_wording_is_role_neutral_and_urls_are_removed(self):
        final = self.build("A woman walks forward. https://example.test/ref.png",
                           references={"images": ["https://example.test/ref.png"]}, duration=8)
        self.assertIn("relevant supplied visual reference attributes", final)
        self.assertNotIn("character reference", final)
        self.assertNotIn("https://", final)

    def test_explicit_character_reference_can_be_character_specific(self):
        final = self.build("A woman smiles.", references={"character": ["ref"]}, duration=8)
        self.assertIn("explicitly identified character reference", final)

    def test_locations_and_capitalized_style_words_are_not_characters(self):
        for prompt in ("Tokyo at night.", "Japan in the Morning.", "Cinematic landscape."):
            context = quality_filter.analyze_prompt_context(prompt)
            self.assertFalse(context["has_character"], prompt)
            self.assertNotIn("micro-expression", self.build(prompt))

    def test_short_duration_condenses_dense_action(self):
        prompt = "A man enters, walks to a desk, opens a box, then turns and runs outside."
        short = self.build(prompt, family="seedance25", duration=4)
        long = self.build(prompt, family="seedance25", duration=25)
        self.assertIn("short duration", short)
        self.assertNotIn("available duration", short)
        self.assertIn("available duration", long)
        self.assertGreater(len(long), len(short))

    def test_model_profiles_have_meaningful_verbosity_difference(self):
        prompt = "A woman walks into a room, opens a box, then looks at a man and smiles."
        wan = self.build(prompt, family="wan30", duration=18)
        seedance25 = self.build(prompt, family="seedance25", duration=18)
        self.assertGreater(len(seedance25), len(wan))

    def test_max_chars_compacts_without_losing_user_intent(self):
        prompt = "A woman walks to a table, then opens a letter and looks toward the door."
        final = self.build(prompt, family="seedance25", duration=20, max_chars=150)
        self.assertLessEqual(len(final), 150)
        self.assertTrue(final.startswith("A woman walks") or final.startswith("SCENE:\nA woman walks"))

    def test_dialogue_is_preserved_exactly_and_not_invented(self):
        dialogue = 'A woman pauses and says, "Tunggu aku, please." Then she smiles.'
        final = self.build(dialogue, family="seedance25", duration=10)
        self.assertIn(dialogue, final)
        self.assertEqual(final.count('"Tunggu aku, please."'), 1)

    def test_contextual_time_lighting_and_grade(self):
        final = self.build("A woman walks through Tokyo at malam.", family="seedance25", duration=8)
        self.assertIn("motivated low-light exposure", final)
        self.assertIn("cool-nocturnal grade", final)

    def test_no_generic_quality_spam(self):
        final = self.build("A person walks home.", family="seedance25", duration=8).lower()
        for spam in ("masterpiece", "8k", "best quality"):
            self.assertNotIn(spam, final)


if __name__ == "__main__":
    unittest.main()
