# ui_components.py

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QCompleter,
                             QPushButton, QLineEdit, QTextEdit, QGroupBox, QLabel,
                             QAbstractItemView)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QTextCursor, QPalette, QIcon

class EditableListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.InternalMove); self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAcceptDrops(True); self.setDefaultDropAction(Qt.MoveAction)
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F2:
            item = self.currentItem()
            if item: self.editItem(item)
        else: super().keyPressEvent(event)

class CompleterTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._completer = QCompleter(self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        # visibleChanged 시그널 연결 제거

    def setModel(self, model):
        if self._completer.model():
            try: self._completer.activated.disconnect(self.insertCompletion)
            except RuntimeError: pass
        self._completer.setModel(model)
        if model:
            self._completer.activated.connect(self.insertCompletion)

    def completer(self): return self._completer

    @Slot(str)
    def insertCompletion(self, completion):
        tc = self.textCursor(); prefix = self.completer().completionPrefix()
        tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(prefix) + 1)
        tc.insertText("{" + completion + "}"); self.setTextCursor(tc)

    def textUnderCursor(self):
        tc = self.textCursor(); block_text = tc.block().text(); pos_in_block = tc.positionInBlock()
        text_before_cursor = block_text[:pos_in_block]; last_brace_pos = text_before_cursor.rfind('{')
        if last_brace_pos != -1:
            suffix = text_before_cursor[last_brace_pos:]
            if '}' not in suffix and ' ' not in suffix and '\n' not in suffix:
                return text_before_cursor[last_brace_pos + 1:]
        return ""

    def keyPressEvent(self, e):
        if self._completer and self._completer.popup().isVisible():
            if e.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape, Qt.Key_Tab, Qt.Key_Backtab):
                e.ignore(); return
        
        super().keyPressEvent(e)
        prefix = self.textUnderCursor()
        if not self._completer or (not prefix and e.text() != '{'):
            self._completer.popup().hide(); return
            
        if self._completer.completionPrefix() != prefix:
            self._completer.setCompletionPrefix(prefix)

        # *** 수정됨: complete() 호출 직후, 팝업의 현재 행을 0으로 설정 ***
        cr = self.cursorRect()
        cr.setWidth(300) 
        self._completer.complete(cr)
        # 팝업이 나타나도록 요청한 후, 즉시 첫 번째 항목을 선택하도록 설정
        self._completer.popup().setCurrentIndex(self._completer.completionModel().index(0, 0))


# ... 나머지 클래스는 변경 없음 ...
class VariablePanel(QGroupBox):
    def __init__(self, title="1. 변수 관리"):
        super().__init__(title)
        layout = QVBoxLayout(self); self.list_widget = EditableListWidget(); layout.addWidget(self.list_widget)
        btn_layout = QHBoxLayout(); self.add_btn = QPushButton("+"); self.remove_btn = QPushButton("-")
        btn_layout.addWidget(self.add_btn); btn_layout.addWidget(self.remove_btn); layout.addLayout(btn_layout)
        layout.addWidget(QLabel("변수 이름:")); self.name_edit = QLineEdit(); layout.addWidget(self.name_edit)
        reserved_label = QLabel("(예약어: RESPONSE)"); palette = reserved_label.palette()
        palette.setColor(QPalette.WindowText, Qt.gray); reserved_label.setPalette(palette); layout.addWidget(reserved_label)
        layout.addWidget(QLabel("변수 내용 (자동완성: '{' 입력):")); self.value_edit = CompleterTextEdit(); layout.addWidget(self.value_edit)
        self.load_file_btn = QPushButton("파일 내용 불러오기..."); layout.addWidget(self.load_file_btn)
class TaskPanel(QGroupBox):
    def __init__(self, title="2. 태스크 관리 (실행 순서)"):
        super().__init__(title)
        layout = QVBoxLayout(self)
        all_check_layout = QHBoxLayout()
        self.check_all_btn = QPushButton("모두 활성화"); self.uncheck_all_btn = QPushButton("모두 비활성화")
        all_check_layout.addWidget(self.check_all_btn); all_check_layout.addWidget(self.uncheck_all_btn); layout.addLayout(all_check_layout)
        self.list_widget = EditableListWidget(); layout.addWidget(self.list_widget)
        btn_layout = QHBoxLayout()
        self.up_btn = QPushButton("▲"); self.down_btn = QPushButton("▼"); self.add_btn = QPushButton("+")
        self.copy_btn = QPushButton("복사"); self.remove_btn = QPushButton("-")
        btn_layout.addWidget(self.up_btn); btn_layout.addWidget(self.down_btn); btn_layout.addStretch()
        btn_layout.addWidget(self.add_btn); btn_layout.addWidget(self.copy_btn); btn_layout.addWidget(self.remove_btn)
        layout.addLayout(btn_layout)
        layout.addWidget(QLabel("태스크 이름 ({변수명} 사용 가능):"))
        self.name_edit = QLineEdit(); layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("프롬프트 템플릿 (자동완성: '{' 입력):"))
        self.prompt_edit = CompleterTextEdit(); layout.addWidget(self.prompt_edit)
        layout.addWidget(QLabel("저장 내용 템플릿:"))
        self.output_template_edit = CompleterTextEdit(); layout.addWidget(self.output_template_edit)
        template_info_label = QLabel("({RESPONSE} 등 내장 변수와 사용자 변수 사용 가능)")
        palette = template_info_label.palette(); palette.setColor(QPalette.WindowText, Qt.gray); template_info_label.setPalette(palette)
        layout.addWidget(template_info_label)
class RunPanel(QGroupBox):
    def __init__(self, title="3. 실행 및 설정"):
        super().__init__(title)
        layout = QVBoxLayout(self); layout.addWidget(QLabel("Gemini API Key:")); self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password); layout.addWidget(self.api_key_edit); layout.addWidget(QLabel("Gemini 모델:"))
        self.model_name_edit = QLineEdit(); layout.addWidget(self.model_name_edit); layout.addWidget(QLabel("결과 저장 폴더:"))
        folder_layout = QHBoxLayout(); self.output_folder_edit = QLineEdit(); self.select_folder_btn = QPushButton("선택")
        self.open_output_folder_btn = QPushButton("열기"); folder_layout.addWidget(self.output_folder_edit)
        folder_layout.addWidget(self.select_folder_btn); folder_layout.addWidget(self.open_output_folder_btn)
        layout.addLayout(folder_layout); layout.addWidget(QLabel("결과 파일 확장자:")); self.output_ext_edit = QLineEdit()
        layout.addWidget(self.output_ext_edit); layout.addWidget(QLabel("로그 저장 폴더 (선택 사항):"))
        log_folder_layout = QHBoxLayout(); self.log_folder_edit = QLineEdit(); self.select_log_folder_btn = QPushButton("선택")
        self.open_log_folder_btn = QPushButton("열기"); log_folder_layout.addWidget(self.log_folder_edit)
        log_folder_layout.addWidget(self.select_log_folder_btn); log_folder_layout.addWidget(self.open_log_folder_btn)
        layout.addLayout(log_folder_layout); layout.addStretch(); self.run_btn = QPushButton("▶ 실행")
        self.run_btn.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;"); self.stop_btn = QPushButton("■ 중지")
        self.stop_btn.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px; color: red;"); self.stop_btn.hide()
        run_stop_layout = QHBoxLayout(); run_stop_layout.addWidget(self.run_btn); run_stop_layout.addWidget(self.stop_btn)
        layout.addLayout(run_stop_layout); log_header_layout = QHBoxLayout(); log_header_layout.addWidget(QLabel("실행 로그:"))
        log_header_layout.addStretch(); self.clear_log_btn = QPushButton("로그 지우기"); log_header_layout.addWidget(self.clear_log_btn)
        layout.addLayout(log_header_layout); self.log_viewer = QTextEdit(); self.log_viewer.setReadOnly(True); layout.addWidget(self.log_viewer)