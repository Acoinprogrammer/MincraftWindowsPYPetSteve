import sys
from PySide6.QtWidgets import QApplication, QLabel, QMenu
from PySide6.QtGui import QMovie, QAction
from PySide6.QtCore import Qt, QPoint
from PySide6.QtCore import QSize

class DesktopPet(QLabel):
    def __init__(self):
        super().__init__()

        # 1. 窗口属性：无边框 + 置顶 + 透明
        self.setWindowFlags(
            Qt.FramelessWindowHint      # 无边框
            | Qt.WindowStaysOnTopHint   # 置顶
            | Qt.Tool                   # 不在任务栏显示
        )
        self.setAttribute(Qt.WA_TranslucentBackground)  # 背景透明

        # 2. 用 QMovie 加载 GIF（替换原来的 QPixmap）
        self.movie = QMovie("待机动画.gif")
        # self.setMovie(self.movie)
        # self.movie.start()
        self.movie.setScaledSize(QSize(345, 200))  # 强制缩放
        self.setMovie(self.movie)
        self.movie.start()
        self.resize(150, 150)

        # 每换一帧就把窗口调整到当前帧大小
        self.movie.frameChanged.connect(self.adjust_size)

        # 3. 拖动相关
        self.dragging = False
        self.offset = QPoint()

    def adjust_size(self):
        # 让窗口尺寸跟随当前帧，避免裁剪或留白
        self.resize(self.movie.currentPixmap().size())

    # ---------- 鼠标拖动 ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.dragging:
            # 窗口新位置 = 鼠标全局位置 - 按下时的偏移
            new_pos = event.globalPosition().toPoint() - self.offset
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        self.dragging = False

    # ---------- 右键菜单 ----------
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())