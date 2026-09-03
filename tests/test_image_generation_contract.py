from pathlib import Path
import unittest

import budgetpixel_provider as provider


class ImageGenerationContractTests(unittest.TestCase):
    def test_flux2_klein_exact_settings_and_no_video_fields(self):
        incoming = {"aspect_ratio": "16:9", "megapixel": 1, "num_images": 1,
                    "duration": 10, "resolution": "720p", "audio_urls": ["bad"]}
        body = provider.build_image_payload("flux2", "KLEIN", incoming, "unaltered image prompt")
        self.assertEqual(body, {"prompt": "unaltered image prompt", "aspect_ratio": "16:9",
                                "megapixel": 1, "num_images": 1})

    def test_flux2_klein_complete_ratio_contract(self):
        expected = {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
                    "21:9", "9:21", "5:4", "4:5", "match_input_image"}
        self.assertEqual(set(provider.image_capabilities("flux2", "KLEIN")["aspect_ratios"]), expected)
        for ratio in expected - {"match_input_image"}:
            body = provider.build_image_payload("flux2", "KLEIN",
                {"aspect_ratio": ratio, "megapixel": "1", "num_images": 1}, "x")
            self.assertEqual(body["aspect_ratio"], ratio)

    def test_match_input_requires_reference_and_seed_is_optional(self):
        data = {"aspect_ratio": "match_input_image", "megapixel": 1, "num_images": 1}
        with self.assertRaises(provider.ProviderError):
            provider.build_image_payload("flux2", "KLEIN", data, "x")
        body = provider.build_image_payload("flux2", "KLEIN", data, "x", ["https://cdn/ref.jpg"])
        self.assertNotIn("seed", body)
        self.assertEqual(body["reference_images"], ["https://cdn/ref.jpg"])

    def test_qwen_count_and_seedream_resolution_are_model_specific(self):
        qwen = provider.build_image_payload("qwenbp", "STANDARD",
            {"aspect_ratio": "3:2", "num_images": 4, "megapixel": 4}, "x")
        self.assertEqual(qwen, {"prompt": "x", "aspect_ratio": "3:2", "num_images": 4})
        seedream = provider.build_image_payload("seedream5", "PRO",
            {"aspect_ratio": "16:9", "size": "2K", "num_images": 2}, "x")
        self.assertEqual(seedream["size"], "2K")
        self.assertNotIn("megapixel", seedream)

    def test_result_urls_are_position_sorted_and_deduplicated(self):
        result = provider.normalize_result({"status": "succeeded", "images": [
            {"url": "https://x/b", "position": 2}, {"url": "https://x/a", "position": 1},
            {"url": "https://x/a", "position": 3}]})
        self.assertEqual(result["images"], [{"url": "https://x/a"}, {"url": "https://x/b"}])

    def test_tier_specific_payload_translation(self):
        pro = provider.build_image_payload("flux2", "PRO",
            {"aspect_ratio":"4:3", "size":"0.5MP", "num_images":1}, "x", ["https://x/ref"])
        self.assertEqual(pro["size"], "0.5MP")
        self.assertEqual(pro["image"], "https://x/ref")
        self.assertNotIn("megapixel", pro)
        dev = provider.build_image_payload("flux2", "DEV",
            {"aspect_ratio":"3:2", "num_images":4}, "x", ["1", "2", "3", "4"])
        self.assertNotIn("size", dev); self.assertNotIn("megapixel", dev)
        self.assertEqual(len(dev["reference_images"]), 4)

    def test_seedream_and_kling_contracts(self):
        lite = provider.build_image_payload("seedream5", "LITE",
            {"aspect_ratio":"21:9", "size":"3K", "num_images":2,
             "sequential_image_generation":"auto", "max_images":14}, "x")
        self.assertEqual((lite["size"], lite["max_images"]), ("3K", 14))
        v3 = provider.build_image_payload("klingimage", "V3",
            {"aspect_ratio":"1:1", "size":"2K", "num_images":1, "negative_prompt":"keep"},
            "x", ["https://x/ref"])
        self.assertEqual(v3["image"], "https://x/ref")
        self.assertNotIn("negative_prompt", v3)
        self.assertEqual(provider.image_capabilities("klingimage", "OMNI")["reference_images"], 9)

    def test_invalid_explicit_values_never_fallback(self):
        for data in ({"aspect_ratio":"7:5", "megapixel":1, "num_images":1},
                     {"aspect_ratio":"1:1", "megapixel":99, "num_images":1}):
            with self.assertRaises(provider.ProviderError) as caught:
                provider.build_image_payload("flux2", "KLEIN", data, "x")
            self.assertEqual(caught.exception.code, "INVALID_INPUT")

    def test_frontend_has_stable_completion_and_original_preview_contract(self):
        source = Path("templates/ai-video.html").read_text()
        for token in ("state.completionHandled", "meta.sourceTaskId = taskId",
                      "object-fit:contain", "imgEl.naturalWidth", "delete body.duration"):
            self.assertIn(token, source)
        self.assertIn("v !== 'match_input_image' || media.image.length > 0", source)


if __name__ == "__main__":
    unittest.main()
