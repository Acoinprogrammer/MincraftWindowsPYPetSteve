import sys
from PySide6.QtWidgets import QApplication, QLabel, QMenu
from PySide6.QtGui import QMovie, QAction
from PySide6.QtCore import Qt, QPoint, QSize, QRect

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
        # state: "idle" / "click" / "drag"
        self.state = "idle"
        self.idle_gif = "待机动画.gif"
        self.click_left_gif  = "点击左臂动画.gif"
        self.click_right_gif = "点击右臂动画.gif"
        self.leg_left_gif    = "点击左腿动画.gif"
        self.leg_right_gif   = "点击右腿动画.gif"
        self.body_gif        = "点击身体动画.gif"
        self.drag_gif        = "长按动画.gif"      # ← 新增

        self.movie = QMovie(self.idle_gif)
        self.movie.setScaledSize(QSize(DISP_W, DISP_H))
        self.setMovie(self.movie)
        self.movie.start()
        self.resize(DISP_W, DISP_H)

        self.movie.frameChanged.connect(self.adjust_size)
        self.movie.finished.connect(self.on_movie_finished)

        # ====== 左臂区域（原图坐标）======
        arm_left_left   = min(250, 292, 252, 293)
        arm_left_right  = max(250, 292, 252, 293)
        arm_top         = min(111, 111, 251, 251)
        arm_bottom      = max(111, 111, 251, 251)

        # ====== 左腿区域（原图坐标）======
        leg_left_left  = min(326, 352, 325, 348) - 9
        leg_left_right = max(326, 352, 325, 348)
        leg_top        = min(242, 242, 385, 385)
        leg_bottom     = max(242, 242, 385, 385) + 10

        # ====== 身体区域（原图坐标）======
        body_left   = 314
        body_right  = 394
        body_top    = 118
        body_bottom = 228

        # 换算到显示坐标的辅助函数
        def to_disp(l, r, t, b):
            l = int(l * SCALE_X)
            r = int(r * SCALE_X)
            t = int(t * SCALE_Y)
            b = int(b * SCALE_Y)
            return QRect(l, t, r - l, b - t)

        # 左臂 + 右臂（右臂=左臂镜像）
        self.left_arm_rect  = to_disp(arm_left_left, arm_left_right,
                                      arm_top, arm_bottom)
        self.right_arm_rect = to_disp(GIF_W - arm_left_right, GIF_W - arm_left_left,
                                      arm_top, arm_bottom)

        # 左腿 + 右腿（右腿=左腿镜像）
        self.left_leg_rect  = to_disp(leg_left_left, leg_left_right,
                                      leg_top, leg_bottom)
        self.right_leg_rect = to_disp(GIF_W - leg_left_right, GIF_W - leg_left_left,
                                      leg_top, leg_bottom)

        # 身体
        self.body_rect = to_disp(body_left, body_right, body_top, body_bottom)

        print(f"[调试] 左臂区域: {self.left_arm_rect}")
        print(f"[调试] 右臂区域: {self.right_arm_rect}")
        print(f"[调试] 左腿区域: {self.left_leg_rect}")
        print(f"[调试] 右腿区域: {self.right_leg_rect}")
        print(f"[调试] 身体区域: {self.body_rect}")

        # ====== 拖动相关 ======
        self.dragging = False       # 鼠标是否按下
        self.drag_mode = False      # 是否已进入拖动动画状态
        self.moved = False          # 是否移动超过阈值
        self.offset = QPoint()      # 按下时鼠标在窗口内的偏移
        self.press_pos = QPoint()   # 按下时的窗口内坐标，用于算移动距离

    def adjust_size(self):
        self.resize(self.movie.currentPixmap().size())

    # ---------- 动画切换 ----------
    def play_gif(self, gif_path, new_state):
        """切换到指定 GIF，并设置状态"""
        self.state = new_state
        self.movie.stop()
        self.movie.setFileName(gif_path)
        self.movie.setScaledSize(QSize(DISP_W, DISP_H))
        self.movie.start()

    def play_click(self, gif_path):
        """点击动画：播放一次，播完回待机"""
        if self.state == "click":
            return
        self.play_gif(gif_path, "click")

    def start_drag_anim(self):
        """进入拖动动画：非循环 GIF 靠 finished 重播形成循环，直到松手"""
        if self.drag_mode:
            return
        self.drag_mode = True
        self.play_gif(self.drag_gif, "drag")

    def stop_drag_anim(self):
        """结束拖动动画，回待机"""
        if not self.drag_mode:
            return
        self.drag_mode = False
        self.play_gif(self.idle_gif, "idle")

    def on_movie_finished(self):
        """GIF 播完（仅非循环 GIF 会触发）"""
        if self.state == "click":
            # 点击动画播完 → 回待机
            self.play_gif(self.idle_gif, "idle")
        elif self.state == "drag" and self.drag_mode:
            # 拖动动画播完但还在拖 → 重新播，形成循环
            self.movie.stop()
            self.movie.start()

    # ---------- 鼠标事件 ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.moved = False
            self.press_pos = event.position().toPoint()
            self.offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if not self.dragging:
            return

        cur = event.position().toPoint()
        # 首次超过阈值 → 判定为拖动，播放拖动 GIF
        if not self.moved:
            if (cur - self.press_pos).manhattanLength() >= DRAG_THRESHOLD:
                self.moved = True
                self.start_drag_anim()

        if self.moved:
            new_pos = event.globalPosition().toPoint() - self.offset
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False

            if self.moved:
                # 拖动结束 → 停止拖动动画，回待机
                self.stop_drag_anim()
            else:
                # 没移动 = 点击 → 判断点击区域
                click_pos = event.position().toPoint()
                print(f"点击坐标(显示): {click_pos.x()}, {click_pos.y()}"
                      f"  | 原图≈ {int(click_pos.x()/SCALE_X)}, {int(click_pos.y()/SCALE_Y)}")

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
        menu = QMenu(self)
        quit_action = QAction("退出", self)
        quit_action1 = QAction("推出", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        menu.addAction(quit_action1)
        menu.exec(event.globalPos())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())