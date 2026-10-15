"""Layout and stitching regressions protect row counts and provenance."""
import pytest

from truecell.models import Table
from truecell.stitch import stitch, compatible
from truecell.table import normalize, words_to_grid


def t(page=1, headers=None, rows=None, bbox=(10,10,110,100), detected=True):
    return Table(headers or ["ID","Label","Units","Amt"], rows or [["A","Item","2","10"]], page,bbox,"native",header_detected=detected)


def test_split_row_keeps_both_sources():
    a=t(rows=[["A","Long item","",""]])
    b=t(page=2,rows=[["","continued","3","15"],["B","Next","4","20"]])
    joined,issues=stitch([a,b])
    assert joined[0].rows[0] == ["A","Long item continued","3","15"]
    assert joined[0].provenance[0] == [(1,1),(2,1)]
    assert any(i.code=="split_row_join" for i in issues)


@pytest.mark.parametrize("page,headers,bbox,expected", [
    (2,None,(10,10,110,100),True), (3,None,(10,10,110,100),False),
    (1,None,(10,10,110,100),False), (2,["X","Y"],(10,10,110,100),False),
    (2,None,(60,10,160,100),False), (2,["a","b","c","d"],(10,10,110,100),False)])
def test_join_guards(page,headers,bbox,expected):
    assert compatible(t(),t(page,headers,bbox=bbox)) == expected


def test_headerless_join_flagged():
    joined, issues=stitch([t(),t(page=2,detected=False)])
    assert len(joined)==1
    assert issues[0].code=="inferred_join"


def test_two_tables_same_page_remain_separate():
    joined,_=stitch([t(),t(bbox=(10,200,110,300))])
    assert len(joined)==2


def test_merged_headers_flattened():
    raw=[["Product",None,"Movement",None],["Code","Name","Units","Value"],
         ["A","Thing","2","10"],["B","Other","3","15"]]
    found=normalize(raw,1,(0,0,100,100),"native")
    assert found.headers==["Product | Code","Product | Name","Movement | Units","Movement | Value"]
    assert len(found.rows)==2


def test_footer_removed():
    found=normalize([["Code","Amt"],["A","10"],["Page 1 of 3",""]],1,(0,0,100,100),"native")
    assert found.rows==[["A","10"]]


def test_wrapped_cell_whitespace_normalized():
    found=normalize([["Code","Amt"],["A\nB","10"]],1,(0,0,100,100),"native")
    assert found.rows[0][0]=="A B"


def test_word_grid_preserves_empty_middle_column():
    words=[]
    for r,row in enumerate([["Code","Units","Value"],["A","2","10"],["B","","20"],["C","3","30"]]):
        for c,text in enumerate(row):
            if text:words.append({"x0":10+c*80,"x1":30+c*80,"top":10+r*20,"bottom":20+r*20,"text":text})
    found=words_to_grid(words,1,"native",300,300)
    assert found[0].rows[1]==["B","","20"]


def test_stitch_does_not_mutate_inputs():
    a,b=t(),t(page=2)
    stitch([a,b])
    assert len(a.rows)==len(b.rows)==1


def test_mixed_document_keeps_row_specific_engines():
    from truecell.validate import validate
    a=Table(["Code","Amt"],[["A","12.00"],["B","13.00"]],1,(0,0,100,100),"native-lines")
    b=Table(["Code","Amt"],[["C","1O.00"]],2,(0,0,100,100),"ocr-tesseract",.7)
    joined,_=stitch([a,b])
    assert joined[0].row_engines==["native-lines","native-lines","ocr-tesseract"]
    assert any(i.code=="ocr_digit_risk" and i.page==2 for i in validate(joined[0]))
