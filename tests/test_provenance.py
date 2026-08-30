from pathlib import Path

from atabey.provenance import canonical_text_sha256, sha256_file


def test_canonical_text_hash_is_newline_stable(tmp_path: Path) -> None:
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(b'{"value": 1}\n')
    crlf.write_bytes(b'{"value": 1}\r\n')

    assert canonical_text_sha256(lf) == canonical_text_sha256(crlf)
    assert sha256_file(lf) != sha256_file(crlf)


def test_canonical_text_hash_detects_content_changes(tmp_path: Path) -> None:
    original = tmp_path / "original.md"
    changed = tmp_path / "changed.md"
    original.write_bytes(b"evidence\n")
    changed.write_bytes(b"different\n")

    assert canonical_text_sha256(original) != canonical_text_sha256(changed)


def test_raw_hash_preserves_binary_bytes(tmp_path: Path) -> None:
    first = tmp_path / "first.gz"
    second = tmp_path / "second.gz"
    first.write_bytes(b"\x1f\x8b\r\n")
    second.write_bytes(b"\x1f\x8b\n")

    assert sha256_file(first) != sha256_file(second)