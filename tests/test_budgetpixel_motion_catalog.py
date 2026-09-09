import unittest
from unittest.mock import Mock

import budgetpixel_motion_catalog as catalog
import budgetpixel_provider as transport
import budgetpixel_registry as registry
from budgetpixel_provider import ProviderError


class MotionCatalogTests(unittest.TestCase):
    def test_registry_and_ui_cover_both_models(self):
        slugs = {row["slug"] for row in catalog.registry_rows()}
        self.assertEqual(slugs, {"kling-3-motion-control-std", "dreamactor-m2.0"})
        qualities = catalog.public_ui_families()[0]["qualities"]
        self.assertEqual({q["id"] for q in qualities}, slugs)
        self.assertTrue(all(q["outputKind"] == "motion" for q in qualities))

    def test_payload_contracts(self):
        image = ["https://example.com/a.png"]
        video = ["https://example.com/a.mp4"]
        kling = catalog.build_payload("kling-3-motion-control-std", "walk", image, video)
        self.assertEqual(kling["character_orientation"], "video")
        self.assertTrue(kling["keep_original_sound"])
        dream = catalog.build_payload("dreamactor-m2.0", "", image, video, trim_intro=False)
        self.assertFalse(dream["trim_intro"])
        with self.assertRaises(ProviderError):
            catalog.build_payload("dreamactor-m2.0", "", [], video)

    def test_transport_uses_motion_control_paths(self):
        models = registry.get_registry("", force=True, session=Mock(get=Mock(side_effect=Exception("offline"))))
        response = Mock(status_code=200)
        response.json.return_value = {"id": "job-1"}
        session = Mock(post=Mock(return_value=response))
        transport.submit_model("dreamactor-m2.0", "motion", {"image": "i", "video": "v"},
                               "secret", models, session=session)
        self.assertTrue(session.post.call_args.args[0].endswith("/motion-control/dreamactor-m2.0"))


if __name__ == "__main__":
    unittest.main()
