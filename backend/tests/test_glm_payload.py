"""Tests for the GLM answer parser (no network involved)."""

from __future__ import annotations

import json

from app.schemas.document import BlockType, DocumentType
from app.services.glm_payload import (
    extract_json_payload,
    parse_model_answer,
    strip_code_fences,
)

PAGE_SIZE = [1000, 1400]


def test_strip_code_fences() -> None:
    assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_extract_plain_json() -> None:
    assert extract_json_payload('{"blocks": []}') == {"blocks": []}


def test_extract_json_with_fences() -> None:
    payload = extract_json_payload('```json\n{"blocks": [{"type": "text"}]}\n```')
    assert payload == {"blocks": [{"type": "text"}]}


def test_extract_json_from_prose() -> None:
    answer = 'Конечно! Вот результат:\n{"blocks": [{"type": "text"}]}\nГотово.'
    assert extract_json_payload(answer) == {"blocks": [{"type": "text"}]}


def test_extract_json_handles_nested_braces_and_strings() -> None:
    answer = 'prefix {"blocks": [{"type": "text", "content": "a } b"}]} suffix'
    payload = extract_json_payload(answer)
    assert payload["blocks"][0]["content"] == "a } b"


def test_extract_json_returns_none_for_garbage() -> None:
    assert extract_json_payload("извините, не могу") is None
    assert extract_json_payload("") is None


def test_extract_json_accepts_bare_list() -> None:
    assert extract_json_payload('[{"type": "text", "content": "x"}]') == [
        {"type": "text", "content": "x"}
    ]


# --------------------------------------------------------------------------- #
#  block parsing
# --------------------------------------------------------------------------- #


def test_parse_text_block() -> None:
    payload = {
        "blocks": [{"type": "text", "content": "Договор № 42", "bbox": [10, 20, 300, 40]}]
    }
    answer = parse_model_answer(payload, DocumentType.text_only, PAGE_SIZE)
    assert answer.payload_ok is True
    assert len(answer.blocks) == 1
    block = answer.blocks[0]
    assert block.type is BlockType.text
    assert block.content == "Договор № 42"
    assert block.bbox == [10.0, 20.0, 300.0, 40.0]


def test_parse_type_aliases() -> None:
    payload = {
        "blocks": [
            {"type": "paragraph", "text": "абзац"},
            {"type": "grid", "rows": [["a", "b"]]},
        ]
    }
    answer = parse_model_answer(payload, DocumentType.text_tables, PAGE_SIZE)
    assert [b.type for b in answer.blocks] == [BlockType.text, BlockType.table]


def test_table_rows_are_made_rectangular() -> None:
    payload = {"blocks": [{"type": "table", "rows": [["a", "b", "c"], ["d"]]}]}
    answer = parse_model_answer(payload, DocumentType.text_tables, PAGE_SIZE)
    assert answer.blocks[0].rows == [["a", "b", "c"], ["d", "", ""]]


def test_table_without_rows_is_dropped() -> None:
    payload = {"blocks": [{"type": "table", "rows": []}]}
    answer = parse_model_answer(payload, DocumentType.text_tables, PAGE_SIZE)
    assert answer.blocks == []
    assert answer.warnings


def test_tables_are_dropped_for_text_only_type() -> None:
    payload = {
        "blocks": [
            {"type": "text", "content": "текст"},
            {"type": "table", "rows": [["a"]]},
        ]
    }
    answer = parse_model_answer(payload, DocumentType.text_only, PAGE_SIZE)
    assert [b.type for b in answer.blocks] == [BlockType.text]
    assert any("таблицы" in w for w in answer.warnings)


def test_images_are_dropped_when_not_part_of_the_type() -> None:
    payload = {"blocks": [{"type": "image", "bbox": [0, 0, 100, 100]}]}
    answer = parse_model_answer(payload, DocumentType.text_tables, PAGE_SIZE)
    assert answer.blocks == []
    assert any("изображени" in w for w in answer.warnings)


def test_image_block_keeps_only_geometry() -> None:
    payload = {
        "blocks": [
            {
                "type": "diagram",
                "bbox": [100, 200, 300, 150],
                "content": "не должно попасть в контент",
            }
        ]
    }
    answer = parse_model_answer(payload, DocumentType.text_tables_images, PAGE_SIZE)
    block = answer.blocks[0]
    assert block.type is BlockType.image
    assert block.bbox == [100.0, 200.0, 300.0, 150.0]
    assert block.content == ""


def test_corner_bbox_outside_page_is_converted_to_size() -> None:
    payload = {"blocks": [{"type": "image", "bbox": [900, 1300, 1000, 1400]}]}
    answer = parse_model_answer(payload, DocumentType.text_tables_images, PAGE_SIZE)
    # [900+1000, 1300+1400] would overflow the page, so these are corners
    assert answer.blocks[0].bbox == [900.0, 1300.0, 100.0, 100.0]


def test_image_without_bbox_is_dropped() -> None:
    payload = {"blocks": [{"type": "image"}]}
    answer = parse_model_answer(payload, DocumentType.text_tables_images, PAGE_SIZE)
    assert answer.blocks == []
    assert any("bbox" in w for w in answer.warnings)


def test_unknown_type_is_skipped() -> None:
    payload = {"blocks": [{"type": "footnote", "content": "x"}]}
    answer = parse_model_answer(payload, DocumentType.text_only, PAGE_SIZE)
    assert answer.blocks == []
    assert any("неизвестный тип" in w for w in answer.warnings)


def test_envelope_variants_are_understood() -> None:
    for envelope in (
        {"blocks": [{"type": "text", "content": "a"}]},
        {"elements": [{"type": "text", "content": "a"}]},
        {"page": {"blocks": [{"type": "text", "content": "a"}]}},
        [{"type": "text", "content": "a"}],
    ):
        answer = parse_model_answer(envelope, DocumentType.text_only, PAGE_SIZE)
        assert len(answer.blocks) == 1, envelope


def test_empty_answer_reports_warning() -> None:
    answer = parse_model_answer({}, DocumentType.text_only, PAGE_SIZE)
    assert answer.payload_ok is False
    assert answer.blocks == []
    assert answer.warnings


def test_bbox_given_as_a_dict_is_understood() -> None:
    payload = {"blocks": [{"type": "image", "bbox": {"x": 10, "y": 20, "w": 30, "h": 40}}]}
    answer = parse_model_answer(payload, DocumentType.text_tables_images, PAGE_SIZE)
    assert answer.blocks[0].bbox == [10.0, 20.0, 30.0, 40.0]


def test_json_roundtrip_of_realistic_answer() -> None:
    answer_text = json.dumps(
        {
            "blocks": [
                {"type": "text", "content": "Акт", "bbox": [50, 50, 200, 30]},
                {"type": "table", "rows": [["A", "1"], ["B", "2"]]},
                {"type": "image", "bbox": [60, 700, 400, 250]},
            ]
        }
    )
    payload = extract_json_payload(answer_text)
    parsed = parse_model_answer(payload, DocumentType.text_tables_images, PAGE_SIZE)
    assert [b.type for b in parsed.blocks] == [
        BlockType.text,
        BlockType.table,
        BlockType.image,
    ]
