# cache_manager_dialog.py

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
                             QListWidget, QTextEdit, QPushButton, QListWidgetItem,
                             QMessageBox, QWidget, QLabel, QInputDialog)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QFont
import os
import datetime

from new_cache_dialog import NewCacheDialog

KST = datetime.timezone(datetime.timedelta(hours=9))

class CacheManagerDialog(QDialog):
    refresh_requested = Signal()
    details_requested = Signal(str)
    delete_requested = Signal(str)
    update_ttl_requested = Signal(str, datetime.timedelta)
    create_requested = Signal(dict)

    # *** 수정됨: 생성자에 supported_models 인자 추가 ***
    def __init__(self, supported_models, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Context Cache 관리자")
        self.setMinimumSize(800, 600)
        
        # *** 수정됨: 모델 목록을 내부 속성으로 저장 ***
        self.supported_models = supported_models

        self.current_cache_name = None; self.current_expire_time = None; self.current_details_text = ""
        self.ttl_timer = QTimer(self); self.ttl_timer.setInterval(1000)
        self.ttl_timer.timeout.connect(self.update_remaining_time)
        self.list_widget = QListWidget()
        self.details_viewer = QTextEdit(); self.details_viewer.setReadOnly(True)
        self.details_viewer.setFont(QFont("Courier New", 10))
        details_widget = QWidget(); details_layout = QVBoxLayout(details_widget)
        details_layout.addWidget(self.details_viewer)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.list_widget); splitter.addWidget(details_widget); splitter.setSizes([300, 500])
        self.refresh_btn = QPushButton("새로고침"); self.new_cache_btn = QPushButton("새 캐시 생성...")
        self.ttl_btn = QPushButton("TTL 재설정"); self.delete_btn = QPushButton("선택 캐시 삭제")
        self.close_btn = QPushButton("닫기")
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.refresh_btn); button_layout.addWidget(self.new_cache_btn); button_layout.addStretch()
        button_layout.addWidget(self.ttl_btn); button_layout.addWidget(self.delete_btn)
        button_layout.addStretch(); button_layout.addWidget(self.close_btn)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(splitter); main_layout.addLayout(button_layout)
        self.set_controls_enabled(False)
        self.refresh_btn.clicked.connect(self.refresh_requested); self.close_btn.clicked.connect(self.accept)
        self.list_widget.currentItemChanged.connect(self.on_item_selected)
        self.delete_btn.clicked.connect(self.on_delete_button_clicked)
        self.ttl_btn.clicked.connect(self.on_ttl_button_clicked)
        self.new_cache_btn.clicked.connect(self.on_new_cache_button_clicked)

    def set_controls_enabled(self, enabled):
        self.list_widget.setEnabled(enabled)
        item_selected = self.list_widget.currentItem() is not None and self.list_widget.currentItem().data(Qt.UserRole) is not None
        self.ttl_btn.setEnabled(enabled and item_selected)
        self.delete_btn.setEnabled(enabled and item_selected)
        self.refresh_btn.setEnabled(enabled); self.new_cache_btn.setEnabled(enabled); self.close_btn.setEnabled(enabled)
    def showEvent(self, event):
        super().showEvent(event)
        self.list_widget.clear(); self.details_viewer.clear()
        self.set_controls_enabled(False)
        self.refresh_requested.emit()
    def closeEvent(self, event):
        if self.ttl_timer.isActive(): self.ttl_timer.stop()
        super().closeEvent(event)
    @Slot()
    def update_remaining_time(self):
        if not self.current_expire_time: return
        now_utc = datetime.datetime.now(datetime.timezone.utc); remaining = self.current_expire_time - now_utc
        if remaining.total_seconds() > 0:
            days, rem = divmod(remaining.total_seconds(), 86400); hours, rem = divmod(rem, 3600); minutes, seconds = divmod(rem, 60)
            parts = []; 
            if days > 0: parts.append(f"{int(days)}일")
            if hours > 0: parts.append(f"{int(hours)}시간")
            if minutes > 0: parts.append(f"{int(minutes)}분")
            parts.append(f"{int(seconds)}초"); remaining_text = f"남은 시간: {' '.join(parts)}"
        else:
            remaining_text = "남은 시간: 만료됨"; self.ttl_timer.stop()
        self.details_viewer.setText(self.current_details_text + "\n\n" + remaining_text)
    @Slot(dict)
    def update_cache_list(self, caches):
        self.list_widget.blockSignals(True); self.list_widget.clear()
        if not caches:
            self.list_widget.addItem("사용 가능한 캐시가 없습니다.")
        else:
            for name, data in sorted(caches.items(), key=lambda item: item[1]['display_name']):
                item = QListWidgetItem(data['display_name']); item.setData(Qt.UserRole, name); self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)
        self.details_viewer.clear()
        self.set_controls_enabled(True)
    @Slot(QListWidgetItem, QListWidgetItem)
    def on_item_selected(self, current, previous):
        self.ttl_timer.stop(); self.current_expire_time = None; self.details_viewer.clear()
        self.set_controls_enabled(True)
        if current and current.data(Qt.UserRole):
            self.current_cache_name = current.data(Qt.UserRole)
            self.details_viewer.setText(f"'{current.text()}' 상세 정보를 불러오는 중...")
            self.details_requested.emit(self.current_cache_name)
        else:
            self.set_controls_enabled(False); self.current_cache_name = None
            
    # *** 수정됨: 부모 참조 대신 전달받은 모델 목록 사용 ***
    @Slot()
    def on_new_cache_button_clicked(self):
        if not self.supported_models:
            QMessageBox.critical(self, "오류", "사용 가능한 모델 목록이 없습니다.")
            return
        
        dialog = NewCacheDialog(self.supported_models, self)
        if dialog.exec():
            data = dialog.get_data()
            if data:
                self.create_requested.emit(data)
                self.set_controls_enabled(False)
                self.details_viewer.setText(f"'{data['display_name']}' 캐시를 생성하는 중...")
            else:
                QMessageBox.warning(self, "입력 오류", "캐시 표시 이름은 비워둘 수 없습니다.")
    
    @Slot()
    def on_ttl_button_clicked(self):
        if not self.current_cache_name: return
        minutes, ok = QInputDialog.getInt(self, "TTL 재설정", "새로운 TTL 값을 분 단위로 입력하세요:", 
                                           value=60, minValue=1, maxValue=60*24*30)
        if ok:
            new_ttl = datetime.timedelta(minutes=minutes)
            self.update_ttl_requested.emit(self.current_cache_name, new_ttl)
    @Slot()
    def on_delete_button_clicked(self):
        current_item = self.list_widget.currentItem()
        if not current_item or not current_item.data(Qt.UserRole): return
        cache_name_full = current_item.data(Qt.UserRole); cache_display_name = current_item.text()
        reply = QMessageBox.critical(self, "캐시 삭제 확인", 
                                     f"'{cache_display_name}' 캐시를 정말 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(cache_name_full)
            self.set_controls_enabled(False); self.details_viewer.setText(f"'{cache_display_name}' 캐시를 삭제하는 중...")
            self.current_expire_time = None; self.ttl_timer.stop()
    @Slot(object)
    def update_details_view(self, cache_object):
        self.set_controls_enabled(True)
        if not cache_object:
            self.details_viewer.setText("캐시 정보를 불러올 수 없습니다."); return
        self.current_cache_name = getattr(cache_object, 'name', None)
        details = [f"표시 이름: {getattr(cache_object, 'display_name', '')}",
                   f"전체 이름: {self.current_cache_name}", "-" * 40,
                   f"모델: {os.path.basename(getattr(cache_object, 'model_name', 'N/A'))}"]
        create_time_utc = getattr(cache_object, 'create_time', None)
        if create_time_utc: details.append(f"생성 시간 (KST): {create_time_utc.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S')}")
        update_time_utc = getattr(cache_object, 'update_time', None)
        if update_time_utc: details.append(f"업데이트 시간 (KST): {update_time_utc.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S')}")
        expire_time_utc = getattr(cache_object, 'expire_time', None)
        self.current_expire_time = expire_time_utc
        if expire_time_utc:
            details.append(f"만료 시간 (KST): {expire_time_utc.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S')}")
            if not self.ttl_timer.isActive(): self.ttl_timer.start()
        token_count_obj = getattr(cache_object, 'token_count', None)
        if token_count_obj:
            total_tokens = getattr(token_count_obj, 'total_tokens', 'N/A')
            details.append(f"크기 (토큰 수): {total_tokens}")
        self.current_details_text = "\n".join(details)
        self.details_viewer.setText(self.current_details_text); self.update_remaining_time()
    @Slot(str)
    def show_error(self, error_message): 
        self.ttl_timer.stop()
        self.details_viewer.setText(f"오류:\n{error_message}")
        self.set_controls_enabled(True)