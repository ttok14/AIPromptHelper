# variable_handler.py

# *** 수정됨: Qt 임포트 추가 ***
from PySide6.QtCore import QObject, Signal, Slot, QRegularExpression, Qt
from PySide6.QtWidgets import QListWidgetItem, QFileDialog, QMessageBox

import os
from data_models import Variable

class VariableHandlerSignals(QObject):
    state_changed = Signal()
    variables_updated = Signal()
    log_message = Signal(str)

class VariableHandler(QObject):
    # (이하 코드는 이전 버전과 동일)
    def __init__(self, ui_panel, variables_dict):
        super().__init__()
        self.ui = ui_panel
        self.data = variables_dict
        self.signals = VariableHandlerSignals()
        self.is_loading = False
    def connect_signals(self):
        self.ui.add_btn.clicked.connect(self.add_variable)
        self.ui.remove_btn.clicked.connect(self.remove_variable)
        self.ui.list_widget.currentItemChanged.connect(self.on_var_selected)
        self.ui.list_widget.itemChanged.connect(self.on_item_changed)
        self.ui.list_widget.model().rowsMoved.connect(
            lambda: self.signals.log_message.emit("변수 목록 순서가 변경되었습니다."))
        self.ui.list_widget.model().rowsMoved.connect(self.signals.state_changed)
        self.ui.name_edit.editingFinished.connect(self.update_details_from_panel)
        self.ui.value_edit.textChanged.connect(self.update_value_from_panel)
        self.ui.load_file_btn.clicked.connect(self.load_from_file)
    def _generate_unique_name(self, base_name, existing_names):
        if base_name not in existing_names: return base_name
        counter = 2
        while True:
            new_name = f"{base_name} ({counter})"
            if new_name not in existing_names: return new_name
            counter += 1
    @Slot()
    def add_variable(self):
        all_var_names = {v.name for v in self.data.values()}
        unique_name = self._generate_unique_name("새 변수", all_var_names)
        var = Variable(name=unique_name)
        self.data[var.id] = var
        item = QListWidgetItem(var.name); item.setData(Qt.UserRole, var.id)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.ui.list_widget.addItem(item)
        self.ui.list_widget.setCurrentItem(item)
        self.signals.log_message.emit(f"변수 '{var.name}' 추가됨")
        self.signals.variables_updated.emit()
        self.signals.state_changed.emit()
    @Slot()
    def remove_variable(self):
        item = self.ui.list_widget.currentItem()
        if not item: return
        var_id = item.data(Qt.UserRole)
        if var_id in self.data:
            var_name = self.data[var_id].name
            if QMessageBox.question(self.ui, "확인", f"'{var_name}' 변수를 정말 삭제하시겠습니까?") == QMessageBox.Yes:
                del self.data[var_id]
                self.ui.list_widget.takeItem(self.ui.list_widget.row(item))
                self.signals.log_message.emit(f"변수 '{var_name}' 삭제됨")
                self.signals.variables_updated.emit()
                self.signals.state_changed.emit()
    @Slot()
    def update_details_from_panel(self):
        item = self.ui.list_widget.currentItem()
        if not item or self.is_loading: return
        var_id = item.data(Qt.UserRole)
        if var_id in self.data:
            var = self.data[var_id]
            new_name = self.ui.name_edit.text()
            if var.name != new_name:
                other_var_names = {v.name for k, v in self.data.items() if k != var_id}
                if new_name in other_var_names:
                    QMessageBox.warning(self.ui, "이름 중복", f"'{new_name}'은(는) 이미 사용 중인 변수 이름입니다.")
                    self.ui.name_edit.setText(var.name)
                    return
                old_name = var.name
                var.name = new_name
                item.setText(new_name)
                self.signals.log_message.emit(f"변수 이름 변경: '{old_name}' -> '{new_name}'")
                self.signals.variables_updated.emit()
                self.signals.state_changed.emit()
    @Slot()
    def update_value_from_panel(self):
        item = self.ui.list_widget.currentItem()
        if not item or self.is_loading: return
        var_id = item.data(Qt.UserRole)
        if var_id in self.data:
            if self.data[var_id].value != self.ui.value_edit.toPlainText():
                self.data[var_id].value = self.ui.value_edit.toPlainText()
                self.signals.state_changed.emit()
    @Slot(QListWidgetItem)
    def on_item_changed(self, item):
        if self.is_loading or not item: return
        var_id = item.data(Qt.UserRole)
        if var_id in self.data:
            var = self.data[var_id]
            new_name = item.text()
            if var.name != new_name:
                old_name = var.name
                other_var_names = {v.name for k, v in self.data.items() if k != var_id}
                if new_name in other_var_names:
                    QMessageBox.warning(self.ui, "이름 중복", f"'{new_name}'은(는) 이미 사용 중인 변수 이름입니다.")
                    item.setText(old_name)
                    return
                self.signals.log_message.emit(f"변수 이름 변경: '{old_name}' -> '{new_name}'")
                var.name = new_name
                if self.ui.list_widget.currentItem() == item:
                    self.ui.name_edit.blockSignals(True)
                    self.ui.name_edit.setText(new_name)
                    self.ui.name_edit.blockSignals(False)
                self.signals.variables_updated.emit()
                self.signals.state_changed.emit()
    @Slot(QListWidgetItem, QListWidgetItem)
    def on_var_selected(self, current, previous):
        self.is_loading = True
        is_item_selected = current is not None
        self.ui.name_edit.setEnabled(is_item_selected)
        self.ui.value_edit.setEnabled(is_item_selected)
        self.ui.remove_btn.setEnabled(is_item_selected)
        self.ui.load_file_btn.setEnabled(is_item_selected)
        self.signals.variables_updated.emit()
        if current:
            var_id = current.data(Qt.UserRole)
            if var_id in self.data:
                var = self.data[var_id]
                self.ui.name_edit.setText(var.name)
                self.ui.value_edit.setPlainText(var.value)
        else:
            self.ui.name_edit.clear()
            self.ui.value_edit.clear()
        self.is_loading = False
    @Slot()
    def load_from_file(self):
        item = self.ui.list_widget.currentItem()
        if not item: return
        filepath, _ = QFileDialog.getOpenFileName(self.ui, "텍스트 파일 선택", "", "Text Files (*.txt);;All Files (*)")
        if not filepath: return
        try:
            with open(filepath, 'r', encoding='utf-8') as f: content = f.read()
            self.ui.value_edit.insertPlainText(content)
            self.signals.log_message.emit(f"'{os.path.basename(filepath)}' 내용을 현재 변수에 추가함")
            self.signals.state_changed.emit()
        except Exception as e:
            QMessageBox.critical(self.ui, "파일 읽기 오류", str(e))