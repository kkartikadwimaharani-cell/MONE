import budgetpixel_provider
import budgetpixel_registry
import budgetpixel_video_catalog as catalog


def test_public_video_catalog_covers_current_budgetpixel_directory():
    assert len(catalog.VIDEO_CATALOG) == 43
    assert {"grok-imagine-video-1.5", "minimax-h3", "pixverse-v6",
            "wan-2.2-animate-replace", "veo-3.1-fast"} <= set(catalog.VIDEO_CATALOG)


def test_existing_provider_routes_are_not_replaced():
    rows = {row["slug"]: row for row in budgetpixel_registry._fallback_models()}
    assert budgetpixel_provider.resolve_video_model("seedance25", "STANDARD") == "/videos/seedance-2.5"
    assert rows["seedance-2.5"]["family"] == "seedance25"


def test_grok_payload_only_emits_supported_fields():
    body = catalog.build_payload(
        "grok-imagine-video-1.5",
        {"duration": 7, "resolution": "1080p", "aspect_ratio": "9:16",
         "negative_prompt": "must not leak", "unexpected": "must not leak"},
        "A clean product shot",
        generate_audio=True,
    )
    assert body == {"prompt": "A clean product shot", "length_seconds": 7,
                    "resolution": "1080p", "aspect_ratio": "9:16",
                    "generate_audio": True}


def test_unknown_live_video_slug_is_prompt_only():
    assert catalog.build_payload("future-video-4", {"duration": 99, "video": "bad"}, "hello") == {"prompt": "hello"}


def test_registry_promotes_only_live_video_entries():
    remote = [
        {"slug": "future-video-4", "name": "Future", "category": "video", "remote": {}},
        {"slug": "future-image-4", "name": "Future Image", "category": "image", "remote": {}},
    ]
    merged = {row["slug"]: row for row in budgetpixel_registry._merge(remote, True)}
    assert merged["future-video-4"]["handler"] is True
    assert merged["future-video-4"]["endpoint"] == "/v1/videos/future-video-4"
    assert merged["future-image-4"]["handler"] is False


def test_documented_models_response_uses_name_as_slug():
    rows = budgetpixel_registry._remote_rows({"data": [
        {"name": "future-video-5", "type": "video", "credits_per_unit": 10}
    ]})
    assert rows[0]["slug"] == "future-video-5"
    assert rows[0]["category"] == "video"


def test_ui_catalog_has_unique_inline_family_keys():
    families = catalog.public_ui_families()
    assert len(families) == len(catalog.VIDEO_CATALOG)
    assert len({item["key"] for item in families}) == len(families)
    assert all(item["key"].startswith("bpx-") for item in families)
