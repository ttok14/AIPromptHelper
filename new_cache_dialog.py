# new_cache_dialog.py

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLabel, QLineEdit, QTextEdit, QComboBox, 
                             QSpinBox, QPushButton, QDialogButtonBox)
import datetime

class NewCacheDialog(QDialog):
    def __init__(self, model_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("새 Context Cache 생성")
        self.setMinimumWidth(500)

        # 위젯 생성
        self.name_edit = QLineEdit()
        self.model_combo = QComboBox()
        self.model_combo.addItems(model_list)
        
        self.content_edit = QTextEdit()
        self.content_edit.setPlaceholderText("캐시에 미리 저장할 시스템 프롬프트나 데이터를 입력하세요.")
        
        self.ttl_spinbox = QSpinBox()
        self.ttl_spinbox.setSuffix(" 분")
        self.ttl_spinbox.setRange(1, 60 * 24 * 30) # 1분 ~ 30일
        self.ttl_spinbox.setValue(60) # 기본값 1시간

        # 버튼 박스
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # 레이아웃
        form_layout = QFormLayout()
        form_layout.addRow("표시 이름:", self.name_edit)
        form_layout.addRow("기반 모델:", self.model_combo)
        form_layout.addRow("TTL (수명):", self.ttl_spinbox)
        
        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(QLabel("캐시할 내용:"))
        main_layout.addWidget(self.content_edit)
        main_layout.addWidget(button_box)

    def get_data(self):
        """사용자가 입력한 데이터를 딕셔너리 형태로 반환합니다."""
        if not self.name_edit.text().strip():
            return None
            
        return {
            'display_name': self.name_edit.text().strip(),
            'model_name': self.model_combo.currentText(),
            'contents': self.content_edit.toPlainText(),
            'ttl': datetime.timedelta(minutes=self.ttl_spinbox.value())
        }