# -*- coding: utf-8 -*-
"""
트레이/창 아이콘(고양이) 생성기.

외부 아이콘을 받아 쓰지 않고 직접 그린다. 라이선스가 얽히지 않고,
exe 안에 그대로 들어가며, 크기별로 최적화할 수 있다.

    python tools/make_icon.py

결과: assets/cat.png (256), assets/cat.ico (16~256 멀티사이즈)
"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen,
)

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

# 앱 다크 테마와 어울리면서, 밝은 작업표시줄에서도 보이도록
# '밝은 채움 + 짙은 외곽선' 조합을 쓴다.
FUR = QColor("#f8fafc")
FUR_SHADE = QColor("#e2e8f0")
OUTLINE = QColor("#1e293b")
EAR_IN = QColor("#f472b6")
EYE = QColor("#38bdf8")
PUPIL = QColor("#0f172a")
NOSE = QColor("#f472b6")
COLLAR = QColor("#2563eb")


def draw_cat(size, detailed=True):
    """고양이 얼굴을 그린 QImage 반환. size 는 정사각 픽셀."""
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)

    # 256 기준으로 그리고 실제 크기로 스케일한다.
    s = size / 256.0
    painter.scale(s, s)

    stroke = 9.0 if detailed else 13.0     # 작을수록 선을 두껍게 해야 형태가 남는다
    pen = QPen(OUTLINE, stroke, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    # ---- 귀 ----
    # 밑변을 넓게, 끝을 덜 뾰족하게. 밑변은 머리 타원 안쪽에 두어
    # 나중에 머리로 덮이게 한다 (그래야 귀가 붙어 보인다).
    for sign in (-1, 1):
        ear = QPainterPath()
        tip_x = 128 + sign * 88
        ear.moveTo(128 + sign * 30, 108)
        ear.quadTo(128 + sign * 62, 44, tip_x, 30)
        ear.quadTo(128 + sign * 92, 78, 128 + sign * 96, 128)
        ear.closeSubpath()

        painter.setPen(pen)
        painter.setBrush(QBrush(FUR))
        painter.drawPath(ear)

        if detailed:
            inner = QPainterPath()
            inner.moveTo(128 + sign * 46, 104)
            inner.quadTo(128 + sign * 66, 62, 128 + sign * 80, 52)
            inner.quadTo(128 + sign * 82, 92, 128 + sign * 82, 118)
            inner.closeSubpath()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(EAR_IN))
            painter.drawPath(inner)

    # ---- 머리 ----
    painter.setPen(pen)
    painter.setBrush(QBrush(FUR))
    painter.drawEllipse(QRectF(26, 72, 204, 168))

    # ---- 수염 (얼굴보다 먼저: 볼 밑에서 뻗어나오게) ----
    if detailed:
        painter.setPen(QPen(OUTLINE, 5.0, Qt.SolidLine, Qt.RoundCap))
        for sign in (-1, 1):
            for y, length, droop in ((150, 62, -10), (166, 68, 2), (182, 60, 16)):
                painter.drawLine(
                    QPointF(128 + sign * 52, y),
                    QPointF(128 + sign * (52 + length), y + droop),
                )

    # ---- 눈 ----
    eye_y = 152
    if detailed:
        for cx in (94, 162):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(EYE))
            painter.drawEllipse(QPointF(cx, eye_y), 25, 28)

            painter.setBrush(QBrush(PUPIL))
            painter.drawEllipse(QPointF(cx, eye_y + 1), 11, 19)

            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawEllipse(QPointF(cx + 8, eye_y - 11), 7, 7)
            painter.drawEllipse(QPointF(cx - 8, eye_y + 9), 4, 4)
    else:
        # 아주 작을 땐 눈을 단순한 점으로. 디테일 넣으면 뭉개진다.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(PUPIL))
        painter.drawEllipse(QPointF(94, eye_y), 16, 18)
        painter.drawEllipse(QPointF(162, eye_y), 16, 18)

    # ---- 코 + 입 ----
    nose = QPainterPath()
    nose.moveTo(128, 192)
    nose.lineTo(114, 180)
    nose.lineTo(142, 180)
    nose.closeSubpath()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(NOSE))
    painter.drawPath(nose)

    if detailed:
        painter.setPen(QPen(OUTLINE, 6.0, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(104, 188, 24, 20), 200 * 16, 140 * 16)
        painter.drawArc(QRectF(128, 188, 24, 20), 200 * 16, 140 * 16)

    painter.end()
    return image


def image_to_png_bytes(image):
    # QByteArray 를 지역 변수로 붙잡아 둬야 한다. QBuffer(QByteArray()) 처럼
    # 임시객체를 넘기면 파이썬이 곧바로 회수하는데 QBuffer 는 그 포인터를
    # 계속 들고 있어서 접근 위반(0xC0000005)으로 죽는다.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def write_ico(path, images):
    """PNG 를 품은 멀티사이즈 .ico 를 직접 쓴다.

    Qt 는 .ico '쓰기'를 보장하지 않으므로 컨테이너를 직접 만든다.
    (Vista 이후 아이콘 항목에 PNG 를 그대로 넣을 수 있다.)
    """
    blobs = [image_to_png_bytes(img) for img in images]

    header = struct.pack("<HHH", 0, 1, len(blobs))          # reserved, type=icon, count
    offset = len(header) + 16 * len(blobs)

    entries, payload = b"", b""
    for image, blob in zip(images, blobs):
        side = image.width()
        entries += struct.pack(
            "<BBBBHHII",
            0 if side >= 256 else side,     # 256 은 0 으로 표기하는 규약
            0 if side >= 256 else side,
            0, 0, 1, 32,
            len(blob), offset,
        )
        payload += blob
        offset += len(blob)

    with open(path, "wb") as f:
        f.write(header + entries + payload)


def main():
    app = QGuiApplication(sys.argv)          # QPainter 쓰려면 필요
    os.makedirs(ASSETS, exist_ok=True)

    # 16/24 는 디테일을 빼야 형태가 살아남는다.
    sizes = [(16, False), (24, False), (32, True), (48, True),
             (64, True), (128, True), (256, True)]
    images = [draw_cat(size, detailed) for size, detailed in sizes]

    png_path = os.path.join(ASSETS, "cat.png")
    images[-1].save(png_path, "PNG")

    ico_path = os.path.join(ASSETS, "cat.ico")
    write_ico(ico_path, images)

    print(f"wrote {png_path}")
    print(f"wrote {ico_path}  ({len(images)} sizes: "
          f"{', '.join(str(s) for s, _ in sizes)})")


if __name__ == "__main__":
    main()
