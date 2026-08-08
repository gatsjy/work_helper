# -*- coding: utf-8 -*-
"""
창 플래그 회귀 테스트.

제목 표시줄 [X] 가 회색으로 죽는 버그는 이 저장소에서 두 번 났다
(f74d4bd 에서 한 번 고쳤고, 이후 되살아났다).

원인은 PySide6 에서 `flags & ~Qt.SomeFlag` 가 지정한 비트만 지우지 않는다는
것이다. WindowStaysOnTopHint 를 끄려다 WindowCloseButtonHint 까지 날아가고,
그러면 Qt 가 시스템 메뉴 SC_CLOSE 에 MF_GRAYED 를 걸어 창을 닫을 수 없게 된다.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow

import gui


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


class TestFlagArithmeticIsUnsafe:
    """이 동작이 버그의 근원이다. 문서화해 둔다."""

    def test_clearing_a_flag_also_clears_others(self):
        flags = Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowStaysOnTopHint
        cleared = flags & ~Qt.WindowStaysOnTopHint

        assert flags & Qt.WindowCloseButtonHint
        # 지우려던 건 StaysOnTop 하나인데 CloseButtonHint 까지 사라진다.
        assert not (cleared & Qt.WindowCloseButtonHint), (
            "PySide6 동작이 바뀌었다면 좋은 일이다. 하지만 gui.py 는 여전히 "
            "플래그 조작에 의존하지 않아야 한다."
        )


class TestMainWindowKeepsCloseButton:

    def test_close_button_hint_present(self, app):
        window = gui.SetAnalyzerGUI()
        try:
            assert window.windowFlags() & Qt.WindowCloseButtonHint, (
                "제목 표시줄 [X] 가 비활성화된다"
            )
        finally:
            window.deid_widget.shutdown()
            window.log_widget.shutdown()

    def test_close_button_survives_show(self, app):
        window = gui.SetAnalyzerGUI()
        try:
            window.show()
            app.processEvents()
            assert window.windowFlags() & Qt.WindowCloseButtonHint
        finally:
            window.deid_widget.shutdown()
            window.log_widget.shutdown()
            window.hide()

    def test_bring_to_front_does_not_touch_flags(self, app):
        window = QMainWindow()
        window.show()
        app.processEvents()

        before = window.windowFlags()
        gui.bring_to_front(window)
        after = window.windowFlags()

        assert before == after, "bring_to_front 가 windowFlags 를 바꿨다"
        assert after & Qt.WindowCloseButtonHint
        window.hide()

    def test_source_has_no_flag_clearing(self):
        """`& ~Qt.Window...Hint` 패턴이 코드에 다시 들어오지 못하게 막는다."""
        source = open(gui.__file__, encoding="utf-8").read()
        code = "\n".join(
            line for line in source.splitlines()
            if not line.strip().startswith("#")
        )
        assert "& ~Qt.Window" not in code, (
            "windowFlags 비트 제거가 다시 들어왔다. 이 연산은 다른 힌트까지 지운다."
        )
