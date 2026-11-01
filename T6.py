import sys
from PySide6.QtWidgets import QApplication, QLabel, QMenu
from PySide6.QtGui import QMovie, QAction
from PySide6.QtCore import Qt, QPoint, QSize, QRect, QTimer

# ====== GIF 原始尺寸 & 显示尺寸 ======
GIF_W, GIF_H = 713, 400
DISP_W, DISP_H = 345, 200

SCALE_X = DISP_W / GIF_W
SCALE_Y = DISP_H / GIF_H

# 移动超过多少像素才算"拖动"（避免轻微手抖误触）
DRAG_THRESHOLD = 5


class DesktopPet(QLabel):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # ====== 动画状态 ======
        self.state = "enter"
        self.exiting = False

        self.idle_gif = "待机动画.gif"
        self.click_left_gif = "点击左臂动画.gif"
        self.click_right_gif = "点击右臂动画.gif"
        self.leg_left_gif = "点击左腿动画.gif"
        self.leg_right_gif = "点击右腿动画.gif"
        self.body_gif = "点击身体动画.gif"
        self.drag_gif = "长按动画.gif"
        self.exit_gif = "退出动画.gif"
        self.enter_gif = "入场动画.gif"

        # 初始化时直接加载入场动画
        self.movie = QMovie(self.enter_gif)
        self.movie.setScaledSize(QSize(DISP_W, DISP_H))
        self.setMovie(self.movie)

        self.movie.frameChanged.connect(self.adjust_size)
        self.movie.finished.connect(self.on_movie_finished)

        self.movie.start()
        self.resize(DISP_W, DISP_H)

        # ====== 点击区域 (省略，同原代码) ======
        arm_left_left = min(250, 292, 252, 293)
        arm_left_right = max(250, 292, 252, 293)
        arm_top = min(111, 111, 251, 251)
        arm_bottom = max(111, 111, 251, 251)

        leg_left_left = min(326, 352, 325, 348) - 9
        leg_left_right = max(326, 352, 325, 348)
        leg_top = min(242, 242, 385, 385)
        leg_bottom = max(242, 242, 385, 385) + 10

        body_left = 314
        body_right = 394
        body_top = 118
        body_bottom = 228

        def to_disp(l, r, t, b):
            l = int(l * SCALE_X)
            r = int(r * SCALE_X)
            t = int(t * SCALE_Y)
            b = int(b * SCALE_Y)
            return QRect(l, t, r - l, b - t)

        self.left_arm_rect = to_disp(arm_left_left, arm_left_right, arm_top, arm_bottom)
        self.right_arm_rect = to_disp(GIF_W - arm_left_right, GIF_W - arm_left_left, arm_top, arm_bottom)
        self.left_leg_rect = to_disp(leg_left_left, leg_left_right, leg_top, leg_bottom)
        self.right_leg_rect = to_disp(GIF_W - leg_left_right, GIF_W - leg_left_left, leg_top, leg_bottom)
        self.body_rect = to_disp(body_left, body_right, body_top, body_bottom)

        # ====== 拖动相关 ======
        self.dragging = False
        self.drag_mode = False
        self.moved = False
        self.offset = QPoint()
        self.press_pos = QPoint()

    def adjust_size(self):
        self.resize(self.movie.currentPixmap().size())

    # ---------- 动画切换 ----------
    def play_gif(self, gif_path, new_state):
        # 防止重复加载同一个动画导致鬼畜
        if self.state == new_state and self.movie.fileName() == gif_path:
            return

        self.state = new_state
        self.movie.stop()
        self.movie.setFileName(gif_path)
        self.movie.setScaledSize(QSize(DISP_W, DISP_H))
        self.movie.start()

    def play_click(self, gif_path):
        if self.state in ("enter", "click") or self.exiting:
            return
        self.play_gif(gif_path, "click")

    def start_drag_anim(self):
        if self.drag_mode or self.exiting or self.state == "enter":
            return
        self.drag_mode = True
        self.play_gif(self.drag_gif, "drag")

    def stop_drag_anim(self):
        if not self.drag_mode:
            return
        self.drag_mode = False
        self.play_gif(self.idle_gif, "idle")

    def start_exit_anim(self):
        if self.exiting:
            return
        self.exiting = True
        self.dragging = False
        self.drag_mode = False
        self.play_gif(self.exit_gif, "exit")

    def on_movie_finished(self):
        """GIF 播完（仅非循环 GIF 会触发）"""
        if self.state == "enter":
            print("入场动画播放完毕，进入待机。")
            self.play_gif(self.idle_gif, "idle")
        elif self.state == "click":
            self.play_gif(self.idle_gif, "idle")
        elif self.state == "drag" and self.drag_mode:
            self.movie.stop()
            self.movie.start()
        elif self.state == "exit" and self.exiting:
            print("退出动画播放完毕，程序退出。")
            QApplication.quit()

    # ---------- 鼠标事件 ----------
    def mousePressEvent(self, event):
        if self.exiting or self.state == "enter":
            return
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.moved = False
            self.press_pos = event.position().toPoint()
            self.offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.exiting or self.state == "enter" or not self.dragging:
            return

        cur = event.position().toPoint()
        if not self.moved:
            if (cur - self.press_pos).manhattanLength() >= DRAG_THRESHOLD:
                self.moved = True
                self.start_drag_anim()

        if self.moved:
            new_pos = event.globalPosition().toPoint() - self.offset
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if self.exiting or self.state == "enter":
            return
        if event.button() == Qt.LeftButton:
            self.dragging = False

            if self.moved:
                self.stop_drag_anim()
            else:
                click_pos = event.position().toPoint()

                if self.body_rect.contains(click_pos):
                    print("  -> 点中身体 ✅")
                    self.play_click(self.body_gif)
                elif self.left_arm_rect.contains(click_pos):
                    print("  -> 点中左臂 ✅")
                    self.play_click(self.click_left_gif)
                elif self.right_arm_rect.contains(click_pos):
                    print("  -> 点中右臂 ✅")
                    self.play_click(self.click_right_gif)
                elif self.left_leg_rect.contains(click_pos):
                    print("  -> 点中左腿 ✅")
                    self.play_click(self.leg_left_gif)
                elif self.right_leg_rect.contains(click_pos):
                    print("  -> 点中右腿 ✅")
                    self.play_click(self.leg_right_gif)
                else:
                    print("  -> 点到别处 ❌")

            self.moved = False

    def contextMenuEvent(self, event):
        if self.exiting or self.state == "enter":
            return

        menu = QMenu(self)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.start_exit_anim)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())