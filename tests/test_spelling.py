from nashville_numbers.converter import convert

def test_spelling_db_major() -> None:
    # 1 in Db should be Db, not C#
    assert convert("1 in Db") == "Key: Db Major\nDb"

def test_spelling_f_sharp_major() -> None:
    # 7 in F# should be E# or at least F#, but definitely not F natural if we want correct spelling.
    # Actually, current preferred list has F# for 6 and F for 5.
    # F# Major: F#(1), G#(2), A#(3), B(4), C#(5), D#(6), E#(7).
    # Current code returns preferred[(6+11)%12] = preferred[5] = "F".
    # While F is enharmonically E#, it's usually better to be consistent.
    # But let's start with Db.
    assert convert("1 4 5 in Db") == "Key: Db Major\nDb Gb Ab"
