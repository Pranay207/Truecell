"""Application-level render checks for upload and saved results."""
from streamlit.testing.v1 import AppTest
from truecell.models import Result, Table, Issue


def test_initial_ui_loads():
    app=AppTest.from_file("app.py").run(timeout=30)
    assert not app.exception
    assert app.button[0].disabled


def test_result_preview_handles_duplicate_labels_and_ragged_rows():
    result=Result("dummy",[Table(["Same","Same"],[["001","12"],["002","13","extra"]],1,(0,0,10,10),"native")])
    result.issues=[Issue("warning",1,2,3,"Unexpected extra column",table=1)]
    app=AppTest.from_file("app.py")
    app.session_state["conversion"]={"result":result,"xlsx":b"test","name":"test.xlsx"}
    app.run(timeout=30)
    assert not app.exception
    assert app.metric[2].value=="2"
