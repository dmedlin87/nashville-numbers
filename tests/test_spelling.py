from nashville_numbers.converter import convert

def test_spelling_db_major() -> None:
    # 1 in Db should be Db, not C#
    assert convert("1 in Db") == "Key: Db Major\nDb"


def test_spelling_cb_major() -> None:
    assert convert("1 4 5 7 in Cb") == "Key: Cb Major\nCb Fb Gb Bbdim"


def test_spelling_f_sharp_major() -> None:
    assert convert("1 4 5 7 in F#") == "Key: F# Major\nF# B C# E#dim"


def test_spelling_a_sharp_major_is_normalized() -> None:
    assert convert("1 4 5 7 in A#") == "Key: Bb Major\nBb Eb F Adim"
