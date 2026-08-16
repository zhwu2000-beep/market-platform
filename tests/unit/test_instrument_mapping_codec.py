from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_platform.application.instrument_mapping_codec import (
    load_trusted_instrument_mapping_registry,
)
from market_platform.research import TrustedInstrumentMappingRegistry


def _document() -> dict[str, object]:
    return {
        "schema_version": "trusted_instrument_mapping_document/v1",
        "source": {
            "source_id": "fixture",
            "source_version": "1",
            "configuration_fingerprint": None,
        },
        "instruments": [
            {
                "instrument_id": "security.nvda",
                "trading_identity": {"symbol": "NVDA", "venue": "NASDAQ"},
                "asset_class": "equity",
                "trading_currency": "USD",
            }
        ],
        "mappings": [
            {
                "external_identity": {
                    "namespace": "polygon",
                    "external_symbol": "NVDA",
                    "external_venue": "NASDAQ",
                },
                "canonical_instrument_id": "security.nvda",
                "valid_from": "2024-06-10",
                "expires_at": None,
            }
        ],
    }


def _write(path: Path, document: object) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8", newline="")
    return path


def test_minimal_document_constructs_v057_registry(tmp_path: Path) -> None:
    registry = load_trusted_instrument_mapping_registry(
        _write(tmp_path / "mapping.json", _document())
    )
    assert type(registry) is TrustedInstrumentMappingRegistry
    assert registry.mappings[0].canonical_instrument.to_dict() == (
        registry.instruments[0].to_dict()
    )
    assert registry.mappings[0].source.to_dict() == registry.source.to_dict()
    assert registry.to_dict()["fingerprint"] == registry.fingerprint


def test_semantic_registry_fingerprint_ignores_json_format(tmp_path: Path) -> None:
    first = _write(tmp_path / "first.json", _document())
    second = tmp_path / "second.json"
    second.write_text(
        json.dumps(_document(), indent=4, sort_keys=True),
        encoding="utf-8",
        newline="\r\n",
    )
    assert load_trusted_instrument_mapping_registry(first).fingerprint == (
        load_trusted_instrument_mapping_registry(second).fingerprint
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda item: item.update(extra=True),
        lambda item: item.pop("source"),
        lambda item: item.update(schema_version="wrong"),
        lambda item: item["instruments"][0]["trading_identity"].update(symbol="nvda"),
        lambda item: item["mappings"][0].update(valid_from="2024-02-30"),
        lambda item: item["mappings"][0]["external_identity"].update(
            namespace="Polygon"
        ),
    ],
)
def test_strict_document_rejections(tmp_path: Path, mutation: object) -> None:
    document = _document()
    mutation(document)  # type: ignore[operator]
    with pytest.raises(ValueError):
        load_trusted_instrument_mapping_registry(
            _write(tmp_path / "bad.json", document)
        )


def test_duplicate_keys_bom_invalid_utf8_and_nonfinite_rejected(
    tmp_path: Path,
) -> None:
    cases = [
        b'{"schema_version":"x","schema_version":"y"}',
        b"\xef\xbb\xbf{}",
        b"\xff",
        b'{"value":NaN}',
    ]
    for index, body in enumerate(cases):
        path = tmp_path / f"bad-{index}.json"
        path.write_bytes(body)
        with pytest.raises(ValueError):
            load_trusted_instrument_mapping_registry(path)


def test_direct_registry_construction_and_arbitrary_paths_rejected() -> None:
    with pytest.raises(TypeError):
        TrustedInstrumentMappingRegistry()
    with pytest.raises(TypeError):
        load_trusted_instrument_mapping_registry(iter(["mapping.json"]))


def test_codec_public_surface_and_schema_are_exact() -> None:
    from market_platform.application import instrument_mapping_codec

    assert instrument_mapping_codec.__all__ == [
        "load_trusted_instrument_mapping_registry"
    ]
    assert (
        instrument_mapping_codec._DOCUMENT_SCHEMA
        == "trusted_instrument_mapping_document/v1"
    )


def _at(document: dict[str, object], path: tuple[object, ...]) -> dict[str, object]:
    value: object = document
    for part in path:
        value = value[part]  # type: ignore[index]
    assert type(value) is dict
    return value


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "schema_version"),
        ((), "source"),
        ((), "instruments"),
        ((), "mappings"),
        (("source",), "source_id"),
        (("source",), "source_version"),
        (("source",), "configuration_fingerprint"),
        (("instruments", 0), "instrument_id"),
        (("instruments", 0), "trading_identity"),
        (("instruments", 0), "asset_class"),
        (("instruments", 0), "trading_currency"),
        (("instruments", 0, "trading_identity"), "symbol"),
        (("instruments", 0, "trading_identity"), "venue"),
        (("mappings", 0), "external_identity"),
        (("mappings", 0), "canonical_instrument_id"),
        (("mappings", 0), "valid_from"),
        (("mappings", 0), "expires_at"),
        (("mappings", 0, "external_identity"), "namespace"),
        (("mappings", 0, "external_identity"), "external_symbol"),
        (("mappings", 0, "external_identity"), "external_venue"),
    ],
)
def test_every_required_field_is_enforced(
    tmp_path: Path, path: tuple[object, ...], field: str
) -> None:
    document = _document()
    _at(document, path).pop(field)
    with pytest.raises(ValueError, match="missing"):
        load_trusted_instrument_mapping_registry(
            _write(tmp_path / "missing.json", document)
        )


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("source",),
        ("instruments", 0),
        ("instruments", 0, "trading_identity"),
        ("mappings", 0),
        ("mappings", 0, "external_identity"),
    ],
)
def test_unknown_fields_are_rejected_at_every_object_level(
    tmp_path: Path, path: tuple[object, ...]
) -> None:
    document = _document()
    _at(document, path)["unknown"] = "value"
    with pytest.raises(ValueError, match="unknown"):
        load_trusted_instrument_mapping_registry(
            _write(tmp_path / "unknown.json", document)
        )


@pytest.mark.parametrize("root", [None, True, 1, 1.5, "text", [], [1]])
def test_wrong_root_runtime_types_are_rejected(tmp_path: Path, root: object) -> None:
    with pytest.raises(ValueError):
        load_trusted_instrument_mapping_registry(_write(tmp_path / "root.json", root))


def test_exact_file_size_limit_and_growth_rejection(tmp_path: Path) -> None:
    encoded = json.dumps(_document()).encode()
    exact = tmp_path / "exact.json"
    exact.write_bytes(encoded + b" " * (1_048_576 - len(encoded)))
    assert load_trusted_instrument_mapping_registry(exact).mappings
    too_large = tmp_path / "large.json"
    too_large.write_bytes(encoded + b" " * (1_048_577 - len(encoded)))
    with pytest.raises(ValueError, match="maximum file size"):
        load_trusted_instrument_mapping_registry(too_large)


def test_record_order_is_fingerprint_invariant_and_semantics_are_not(
    tmp_path: Path,
) -> None:
    document = _document()
    second = {
        "instrument_id": "security.msft",
        "trading_identity": {"symbol": "MSFT", "venue": "NASDAQ"},
        "asset_class": "equity",
        "trading_currency": "USD",
    }
    second_mapping = {
        "external_identity": {
            "namespace": "polygon",
            "external_symbol": "MSFT",
            "external_venue": "NASDAQ",
        },
        "canonical_instrument_id": "security.msft",
        "valid_from": "1986-03-13",
        "expires_at": None,
    }
    document["instruments"].append(second)  # type: ignore[union-attr]
    document["mappings"].append(second_mapping)  # type: ignore[union-attr]
    reordered = json.loads(json.dumps(document))
    reordered["instruments"].reverse()
    reordered["mappings"].reverse()
    first = load_trusted_instrument_mapping_registry(
        _write(tmp_path / "first.json", document)
    )
    second_registry = load_trusted_instrument_mapping_registry(
        _write(tmp_path / "second.json", reordered)
    )
    assert first.fingerprint == second_registry.fingerprint

    changed = json.loads(json.dumps(document))
    changed["source"]["source_version"] = "2"
    changed_registry = load_trusted_instrument_mapping_registry(
        _write(tmp_path / "changed.json", changed)
    )
    assert first.fingerprint != changed_registry.fingerprint


def test_retained_registry_fingerprint_laundering_fails(tmp_path: Path) -> None:
    registry = load_trusted_instrument_mapping_registry(
        _write(tmp_path / "mapping.json", _document())
    )
    object.__setattr__(registry, "fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="fingerprint"):
        registry.to_dict()


def test_nested_retained_mapping_corruption_raises_value_error(tmp_path: Path) -> None:
    registry = load_trusted_instrument_mapping_registry(
        _write(tmp_path / "mapping.json", _document())
    )
    object.__delattr__(registry._mappings[0], "fingerprint")

    with pytest.raises(ValueError, match="trusted registry retained state"):
        registry.to_dict()
