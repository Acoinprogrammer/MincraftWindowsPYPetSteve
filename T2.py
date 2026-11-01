import sys
from PySide6.QtWidgets import QApplication, QLabel, QMenu
from PySide6.QtGui import QMovie, QAction
from PySide6.QtCore import Qt, QPoint, QSize


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

        # 2. 动画状态
        self.state = "idle"                 # "idle" 或 "click"
        self.idle_gif = "待机动画.gif"
        self.click_gif = "点击左臂动画.gif"      # 如需用左臂，改成 "点击左臂.gif"

        self.movie = QMovie(self.idle_gif)
        self.movie.setScaledSize(QSize(345, 200))  # 强制缩放
        self.setMovie(self.movie)
        self.movie.start()
        self.resize(150, 150)

        # 每换一帧就把窗口调整到当前帧大小
        self.movie.frameChanged.connect(self.adjust_size)
        # 动画播放结束（仅对非循环 GIF 有意义）
        self.movie.finished.connect(self.on_movie_finished)

        # 3. 拖动相关
        self.dragging = False
        self.offset = QPoint()
        self.moved = False   # 本次按下是否发生过移动

    def adjust_size(self):
        # 让窗口尺寸跟随当前帧，避免裁剪或留白
        self.resize(self.movie.currentPixmap().size())

    # ---------- 动画切换 ----------
    def play_click(self):
        """播放点击动画，播完自动回待机"""
        if self.state == "click":
            return  # 正在播放就不重复触发
        self.state = "click"
        self.movie.stop()
        self.movie.setFileName(self.click_gif)
        self.movie.setScaledSize(QSize(345, 200))
        self.movie.start()

    def on_movie_finished(self):
        """点击动画播放完毕，切回待机"""
        if self.state == "click":
            self.state = "idle"
            self.movie.stop()
            self.movie.setFileName(self.idle_gif)
            self.movie.setScaledSize(QSize(345, 200))
            self.movie.start()

    # ---------- 鼠标拖动 & 点击 ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.moved = False
            self.offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.moved = True
            # 窗口新位置 = 鼠标全局位置 - 按下时的偏移
            new_pos = event.globalPosition().toPoint() - self.offset
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            # 没有移动 => 视为点击，播放点击动画
            if not self.moved:
                self.play_click()

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