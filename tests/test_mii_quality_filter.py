import unittest

import mii_quality_filter as quality_filter


class MiiQualityFilterTests(unittest.TestCase):
    def test_is_deterministic_and_removes_exact_repetition(self):
        prompt = "Maya opens the door. Maya opens the door. Then she smiles."
        first = quality_filter.build_final_prompt(prompt, family="seedance", duration=8)
        self.assertEqual(first, quality_filter.build_final_prompt(prompt, family="seedance", duration=8))
        self.assertEqual(first.count("Maya opens the door."), 1)
        self.assertNotIn("masterpiece", first.lower())
        self.assertNotIn("8k", first.lower())

    def test_preserves_explicit_direction_and_dialogue(self):
        prompt = ('Locked camera, close-up, neon midnight lighting, cool blue grade. '
                  'Ari says, "Wait for me."')
        final = quality_filter.build_final_prompt(prompt, family="wan30", duration=5)
        self.assertIn('Ari says, "Wait for me."', final)
        self.assertIn("Locked camera", final)
        self.assertIn("close-up", final)
        self.assertNotIn("motivated environmental light", final)
        self.assertNotIn("color grade natural", final)
        self.assertNotIn("natural reframing", final)

    def test_reference_aware_continuity_is_neutral(self):
        final = quality_filter.build_final_prompt(
            "A woman walks to the window and turns.",
            family="seedance25",
            duration=8,
            references={"images": ["https://example.test/reference.png"]},
        )
        self.assertIn("Preserve the referenced character identity", final)
        self.assertNotIn("follow referenced motion", final)

    def test_short_dense_prompt_prefers_readable_beats(self):
        final = quality_filter.build_final_prompt(
            "A man enters, walks to a desk, reaches for a key, opens a box, then turns and runs.",
            family="seedance",
            duration=4,
        )
        self.assertIn("essential readable beats", final)
        self.assertLessEqual(final.count("Direction:"), 4)

    def test_latest_clear_camera_instruction_wins_conflict(self):
        final = quality_filter.build_final_prompt(
            "Use a static locked camera, but then the camera circles around the subject.",
            family="kling",
        )
        self.assertNotIn("static locked", final.lower())
        self.assertIn("circles around", final.lower())

    def test_model_profile_limits_verbosity(self):
        final = quality_filter.build_final_prompt(
            "A woman walks across a room and looks at a photograph.", family="wan30", duration=10
        )
        self.assertLessEqual(final.count("Direction:"), 3)


if __name__ == "__main__":
    unittest.main()
