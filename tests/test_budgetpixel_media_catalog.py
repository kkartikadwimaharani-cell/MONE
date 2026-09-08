import unittest

import budgetpixel_media_catalog as catalog
import budgetpixel_registry as registry
from budgetpixel_provider import ProviderError


class BudgetPixelMediaCatalogTests(unittest.TestCase):
    def test_catalogue_slugs_are_unique(self):
        rows = catalog.registry_rows()
        slugs = [row["slug"] for row in rows]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertGreaterEqual(len(catalog.IMAGE_ROWS), 45)
        self.assertEqual(len(catalog.AUDIO_ROWS), 8)

    def test_ui_groups_product_variants(self):
        bundle = catalog.public_ui_bundle()
        images = {row["name"]: row for row in bundle["image_families"]}
        audios = {row["name"]: row for row in bundle["audio_families"]}
        self.assertEqual([q["label"] for q in images["QWEN IMAGE 3"]["qualities"]],
                         ["STANDARD", "PRO"])
        self.assertEqual([q["label"] for q in audios["MINIMAX MUSIC"]["qualities"]],
                         ["3.0", "2.6"])
        self.assertEqual([q["label"] for q in audios["SONILO SFX"]["qualities"]],
                         ["TEXT", "VIDEO"])

    def test_all_budgetpixel_midjourney_models_share_one_family(self):
        bundle = catalog.public_ui_bundle()
        images = {row["name"]: row for row in bundle["image_families"]}
        midjourney = images["MIDJOURNEY"]
        self.assertEqual(
            [(q["id"], q["label"]) for q in midjourney["qualities"]],
            [("midjourney-v7", "V7"), ("midjourney-niji-7", "NIJI 7")],
        )
        self.assertTrue(all(not q["caps"]["elements"]
                            for q in midjourney["qualities"]))

    def test_midjourney_payload_is_prompt_only(self):
        for slug in ("midjourney-v7", "midjourney-niji-7"):
            self.assertEqual(
                catalog.build_image_payload(slug, {}, "cinematic portrait"),
                {"prompt": "cinematic portrait"},
            )

    def test_midjourney_stays_visible_when_live_directory_is_partial(self):
        partial = {"models": [{"slug": "some-other-model", "handler": True}],
                   "sync_error": None}
        names = {row["name"] for row in catalog.public_ui_bundle(partial)["image_families"]}
        self.assertIn("MIDJOURNEY", names)

    def test_reviewed_midjourney_handlers_survive_partial_remote_merge(self):
        remote = [{"slug": "some-other-model", "name": "Other",
                   "category": "image", "remote": {}}]
        rows = registry._merge(remote, configured=True)
        slugs = {row["slug"] for row in rows if row.get("handler")}
        self.assertIn("midjourney-v7", slugs)
        self.assertIn("midjourney-niji-7", slugs)

    def test_edit_model_requires_image(self):
        with self.assertRaises(ProviderError):
            catalog.build_image_payload("p-image-edit", {}, "remove object")
        body = catalog.build_image_payload("p-image-edit", {}, "remove object",
                                           reference_images=["https://example.com/a.png"])
        self.assertEqual(body["image"], "https://example.com/a.png")

    def test_music_payloads_use_reviewed_contracts(self):
        body = catalog.build_audio_payload("music-3.0", {"audio_format": "wav"},
                                           "cinematic instrumental")
        self.assertEqual(body["format"], "wav")
        self.assertTrue(body["instrumental"])
        lyria = catalog.build_audio_payload("lyria-3", {}, "ambient score",
                                            reference_images=["https://example.com/a.png"])
        self.assertEqual(lyria["images"], ["https://example.com/a.png"])

    def test_video_audio_requires_video(self):
        with self.assertRaises(ProviderError):
            catalog.build_audio_payload("sonilo-video-music", {}, "match the edit")


if __name__ == "__main__":
    unittest.main()
