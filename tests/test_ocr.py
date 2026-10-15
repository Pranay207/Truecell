"""Image geometry and engine-independent OCR reconstruction regressions."""
import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

from truecell.ocr import grid_regions, preprocess, extract_image, cell_text, rectify_perspective


def make_grid():
    image=Image.new("RGB",(900,500),"white")
    draw=ImageDraw.Draw(image)
    draw.rectangle((40,40,840,110),fill=(25,50,75))
    for x in [40,240,440,640,840]:draw.line((x,40,x,390),fill=(145,160,175),width=3)
    for y in [40,110,180,250,320,390]:draw.line((40,y,840,y),fill=(145,160,175),width=3)
    return image


def test_pale_grid_survives_dark_header():
    gray=cv2.cvtColor(np.asarray(make_grid()),cv2.COLOR_RGB2GRAY)
    regions,_=grid_regions(gray)
    assert len(regions)==1
    assert len(regions[0][0])==5 and len(regions[0][1])==6


@pytest.mark.parametrize("angle",[-7,-3,3,7])
def test_deskew_arbitrary_angle(angle):
    image=make_grid().rotate(angle,fillcolor="white",resample=Image.Resampling.BICUBIC)
    _,correction=preprocess(image)
    assert abs(abs(correction)-abs(angle))<1


def test_grid_box_assignment_preserves_empty_cell(monkeypatch):
    import truecell.ocr as ocr
    words=[]
    rows=[["Code","Label","Units","Value"],["A","Item","2","10"],["B","Other","","15"],
          ["C","Third","4","20"],["D","Last","5","25"]]
    for r,row in enumerate(rows):
        for c,value in enumerate(row):
            if value:words.append({"x0":60+c*200,"x1":130+c*200,"top":60+r*70,"bottom":80+r*70,"text":value,"confidence":.99})
    monkeypatch.setattr(ocr,"recognize",lambda gray,engine:words)
    tables=extract_image(make_grid(),1,"test")
    assert tables[0].headers==rows[0]
    assert tables[0].rows[1]==rows[2]


def test_blank_image_no_invented_table(monkeypatch):
    import truecell.ocr as ocr
    monkeypatch.setattr(ocr,"recognize",lambda gray,engine:[])
    assert extract_image(Image.new("RGB",(500,300),"white"),1,"test")==[]


def test_box_jitter_does_not_reorder_words():
    words=[{"x0":50,"x1":80,"top":10,"bottom":25,"text":"model"},
           {"x0":10,"x1":45,"top":11,"bottom":26,"text":"Widget"},
           {"x0":90,"x1":99,"top":9,"bottom":24,"text":"4"}]
    assert cell_text(words)=="Widget model 4"


def test_rectangular_grid_not_rectified_unnecessarily():
    _,quad=rectify_perspective(make_grid())
    assert quad is None


def test_perspective_grid_detected():
    image=np.asarray(make_grid())
    matrix=cv2.getPerspectiveTransform(np.float32([[0,0],[900,0],[900,500],[0,500]]),
                                      np.float32([[50,30],[840,0],[900,450],[0,500]]))
    warped=Image.fromarray(cv2.warpPerspective(image,matrix,(900,500),borderValue=(255,255,255)))
    _,quad=rectify_perspective(warped)
    assert quad is not None
