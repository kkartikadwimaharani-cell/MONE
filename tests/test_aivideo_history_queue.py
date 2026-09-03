from pathlib import Path
import re
import tempfile
import unittest

import aivideo_archive


class AiVideoHistoryQueueContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("templates/ai-video.html").read_text(encoding="utf-8")

    def body(self, name):
        match = re.search(rf"function {name}\([^)]*\) \{{", self.source)
        self.assertIsNotNone(match, name)
        depth = 1
        for i in range(match.end(), len(self.source)):
            if self.source[i] == "{": depth += 1
            elif self.source[i] == "}":
                depth -= 1
                if not depth: return self.source[match.end():i]
        self.fail(f"unterminated {name}")

    def test_queue_stages_are_mode_specific_and_honest(self):
        stage = self.body("stageForProgress")
        self.assertIn("Preparing ' + mode", stage)
        self.assertIn("Generating ' + mode", stage)
        self.assertNotIn("Generating Motion", stage)
        self.assertNotIn("Rendering Video", stage)
        self.assertNotIn("Uploading Assets", stage)
        self.assertEqual(self.source.count("Generating Motion"), 0)
        self.assertEqual(self.source.count("Rendering Video"), 0)

    def test_queue_card_reads_snapshot_meta(self):
        queue = self.body("genQueueItemHtml")
        for token in ("queueMetaSummary(meta)", "queueReferenceCounts(meta)", "meta.prompt"):
            self.assertIn(token, queue)
        self.assertIn("queueMode(meta)", self.body("queueMetaSummary"))
        self.assertNotIn("selectedFamily", queue)
        self.assertNotIn("promptInput", queue)
        poll = self.body("pollQueueTask")
        self.assertIn("stageForProgress(meta, progress, status)", poll)

    def test_media_classification_and_audio_download(self):
        classify = self.body("recordMediaType")
        self.assertIn("r.videoUrl", classify)
        self.assertIn("r.audioUrl", classify)
        self.assertIn("return 'image'", classify)
        self.assertIn("r.videoUrl || r.imageUrl || r.audioUrl", self.body("downloadHistoryItem"))

    def test_delete_waits_and_preserves_local_on_failure(self):
        delete = self.body("confirmDeleteHistoryItem")
        then_at = delete.index("removeArchiveFromServer(deletingId).then")
        local_at = delete.index("deleteHistoryRecord(deletingId)")
        self.assertLess(then_at, local_at)
        self.assertIn("if (!ok)", delete)
        self.assertIn("window.__lastResult = null", delete)
        self.assertIn("btn.disabled = true", delete)

    def test_archive_is_server_first_and_double_tap_safe(self):
        toggle = self.body("toggleArchiveItem")
        self.assertIn("archiveOpsInFlight[id]", toggle)
        self.assertLess(toggle.index("syncArchiveToServer"), toggle.index("updateHistoryRecord"))
        self.assertIn("if (!ok)", toggle)

    def test_reconciliation_deduplicates_and_rejects_late_mutations(self):
        self.assertIn("dedupeHistoryRecords", self.body("mergeServerHistoryIntoLocal"))
        self.assertIn("dedupeHistoryRecords", self.body("mergeServerArchiveIntoLocal"))
        self.assertIn("requestVersion === historyMutationVersion", self.body("refreshHistoryFromServer"))
        self.assertIn("requestVersion === historyMutationVersion", self.body("refreshArchiveFromServer"))
        self.assertIn("deletedHistoryIds", self.body("dedupeHistoryRecords"))

    def test_snapshot_history_and_multi_image_contract(self):
        save = self.body("saveGenerationToHistory")
        for field in ("imageUrls", "mediaType", "audioEnabled", "refAudios", "referenceCounts", "elapsedMs", "sizeBytes"):
            self.assertIn(field, save)
        self.assertIn("payload.imageUrls", self.body("openResultOverlay"))

    def test_mobile_layout_contract(self):
        self.assertIn("@media(max-width:590px)", self.source)
        self.assertIn("grid-template-columns:repeat(4,1fr)", self.source)
        self.assertIn("grid-template-columns:72px minmax(0,1fr)", self.source)
        self.assertIn("repeat(3,minmax(0,1fr))", self.source)
        # The <=590 rule covers all explicitly required widths.
        for width in (360, 390, 412, 430): self.assertLessEqual(width, 590)


class ArchivePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.old_path, self.old_conn = aivideo_archive._DB_PATH, aivideo_archive._conn
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db.close()
        aivideo_archive._DB_PATH, aivideo_archive._conn = self.db.name, None
        aivideo_archive.init_db()

    def tearDown(self):
        if aivideo_archive._conn: aivideo_archive._conn.close()
        aivideo_archive._DB_PATH, aivideo_archive._conn = self.old_path, self.old_conn
        Path(self.db.name).unlink(missing_ok=True)

    def test_multi_image_and_generation_metadata_round_trip(self):
        rec = {"id":"images", "imageUrl":"one", "imageUrls":["one","two","three"],
               "mediaType":"image", "archived":False, "elapsedMs":1234, "sizeBytes":99,
               "refAudios":["audio-ref"], "audioEnabled":True, "sourceTaskId":"provider-task-1"}
        aivideo_archive.upsert_archive(rec)
        saved = aivideo_archive.list_archive(None)[0]
        self.assertEqual(saved["imageUrls"], rec["imageUrls"])
        self.assertEqual(saved["refAudios"], rec["refAudios"])
        self.assertEqual(saved["elapsedMs"], 1234)
        self.assertEqual(saved["sizeBytes"], 99)
        self.assertTrue(saved["audioEnabled"])
        self.assertFalse(saved["archived"])
        self.assertEqual(saved["sourceTaskId"], "provider-task-1")


if __name__ == "__main__": unittest.main()
