from app.pob.decode import decode_pob_code, encode_pob_code


def test_round_trip():
    xml = "<PathOfBuilding><Build level=\"1\" /></PathOfBuilding>"
    code = encode_pob_code(xml)
    assert decode_pob_code(code) == xml


def test_decode_rejects_garbage():
    import pytest

    with pytest.raises(Exception):
        decode_pob_code("not a real pob code")
