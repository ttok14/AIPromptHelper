# task_handler.py

from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox

from data_models import Task

class TaskHandlerSignals(QObject):
    state_changed = Signal()
    log_message = Signal(str)

class TaskHandler(QObject):
    def __init__(self, ui_panel, tasks_dict):
        super().__init__(); self.ui = ui_panel; self.data = tasks_dict
        self.signals = TaskHandlerSignals(); self.is_loading = False

    def connect_signals(self):
        self.ui.add_btn.clicked.connect(self.add_task)
        self.ui.remove_btn.clicked.connect(self.remove_task)
        self.ui.copy_btn.clicked.connect(self.copy_task)
        self.ui.up_btn.clicked.connect(lambda: self.move_task('up'))
        self.ui.down_btn.clicked.connect(lambda: self.move_task('down'))
        self.ui.list_widget.currentItemChanged.connect(self.on_task_selected)
        self.ui.list_widget.itemChanged.connect(self.on_item_changed)
        self.ui.list_widget.model().rowsMoved.connect(lambda: self.signals.log_message.emit("태스크 목록 순서가 변경되었습니다."))
        self.ui.list_widget.model().rowsMoved.connect(self.signals.state_changed)
        self.ui.name_edit.editingFinished.connect(self.update_details_from_panel)
        # *** 수정됨: 슬롯 연결 대상 함수에 @Slot() 데코레이터가 필요함 ***
        self.ui.prompt_edit.textChanged.connect(self.update_prompt_from_panel)
        self.ui.output_template_edit.textChanged.connect(self.update_template_from_panel)
        self.ui.check_all_btn.clicked.connect(lambda: self.set_all_tasks_checked(True))
        self.ui.uncheck_all_btn.clicked.connect(lambda: self.set_all_tasks_checked(False))
    
    # ... _generate_unique_name, add_task, remove_task, copy_task, move_task, update_details_from_panel 등은 변경 없음 ...
    def _generate_unique_name(self, base_name, existing_names):
        if base_name not in existing_names: return base_name
        counter = 2
        while True:
            new_name = f"{base_name} ({counter})";
            if new_name not in existing_names: return new_name
            counter += 1
    @Slot()
    def add_task(self):
        all_task_names = {t.name for t in self.data.values()}; unique_name = self._generate_unique_name("새 태스크", all_task_names)
        task = Task(name=unique_name); self.data[task.id] = task
        item = QListWidgetItem(task.name); item.setData(Qt.UserRole, task.id)
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if task.enabled else Qt.Unchecked); self.ui.list_widget.addItem(item)
        self.ui.list_widget.setCurrentItem(item); self.signals.log_message.emit(f"태스크 '{task.name}' 추가됨")
        self.signals.state_changed.emit()
    @Slot()
    def remove_task(self):
        item = self.ui.list_widget.currentItem()
        if not item: return
        task_id = item.data(Qt.UserRole)
        if task_id in self.data:
            task_name = self.data[task_id].name
            if QMessageBox.question(self.ui, "확인", f"'{task_name}' 태스크를 정말 삭제하시겠습니까?") == QMessageBox.Yes:
                del self.data[task_id]; self.ui.list_widget.takeItem(self.ui.list_widget.row(item))
                self.signals.log_message.emit(f"태스크 '{task_name}' 삭제됨"); self.signals.state_changed.emit()
    @Slot()
    def copy_task(self):
        item = self.ui.list_widget.currentItem()
        if not item: return
        original_task = self.data[item.data(Qt.UserRole)]; all_task_names = {t.name for t in self.data.values()}
        base_name = f"{original_task.name} (복사본)"; unique_name = self._generate_unique_name(base_name, all_task_names)
        new_task = Task(name=unique_name, prompt=original_task.prompt, 
                        output_template=original_task.output_template, enabled=original_task.enabled)
        self.data[new_task.id] = new_task; new_item = QListWidgetItem(new_task.name); new_item.setData(Qt.UserRole, new_task.id)
        new_item.setFlags(new_item.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
        new_item.setCheckState(Qt.Checked if new_task.enabled else Qt.Unchecked); current_row = self.ui.list_widget.row(item)
        self.ui.list_widget.insertItem(current_row + 1, new_item); self.ui.list_widget.setCurrentItem(new_item)
        self.signals.log_message.emit(f"태스크 '{original_task.name}' 복사됨 -> '{new_task.name}'"); self.signals.state_changed.emit()
    @Slot(str)
    def move_task(self, direction):
        list_widget = self.ui.list_widget; item = list_widget.currentItem();
        if not item: return
        current_row = list_widget.row(item); new_row = -1
        if direction == 'up' and current_row > 0: new_row = current_row - 1
        elif direction == 'down' and current_row < list_widget.count() - 1: new_row = current_row + 1
        if new_row != -1:
            list_widget.takeItem(current_row); list_widget.insertItem(new_row, item); list_widget.setCurrentRow(new_row)
    @Slot()
    def update_details_from_panel(self):
        item = self.ui.list_widget.currentItem()
        if not item or self.is_loading: return
        task_id = item.data(Qt.UserRole)
        if task_id in self.data:
            task = self.data[task_id]
            new_name = self.ui.name_edit.text()
            if task.name != new_name:
                other_task_names = {t.name for k, t in self.data.items() if k != task_id}
                if new_name in other_task_names:
                    QMessageBox.warning(self.ui, "이름 중복", f"'{new_name}'은(는) 이미 사용 중인 태스크 이름입니다.")
                    self.ui.name_edit.setText(task.name)
                    return
                task.name = new_name; item.setText(new_name); self.signals.state_changed.emit()
    
    # *** 수정됨: @Slot() 데코레이터 추가 ***
    @Slot()
    def update_prompt_from_panel(self):
        item = self.ui.list_widget.currentItem()
        if not item or self.is_loading: return
        task_id = item.data(Qt.UserRole)
        if task_id in self.data and self.data[task_id].prompt != self.ui.prompt_edit.toPlainText():
            self.data[task_id].prompt = self.ui.prompt_edit.toPlainText()
            self.signals.state_changed.emit()

    # *** 수정됨: @Slot() 데코레이터 추가 ***
    @Slot()
    def update_template_from_panel(self):
        item = self.ui.list_widget.currentItem()
        if not item or self.is_loading: return
        task_id = item.data(Qt.UserRole)
        if task_id in self.data and self.data[task_id].output_template != self.ui.output_template_edit.toPlainText():
            self.data[task_id].output_template = self.ui.output_template_edit.toPlainText()
            self.signals.state_changed.emit()

    @Slot(QListWidgetItem)
    def on_item_changed(self, item):
        if self.is_loading or not item: return
        task_id = item.data(Qt.UserRole)
        if task_id in self.data:
            task = self.data[task_id]; new_name = item.text()
            if task.name != new_name:
                old_name = task.name; other_task_names = {t.name for k, t in self.data.items() if k != task_id}
                if new_name in other_task_names:
                    QMessageBox.warning(self.ui, "이름 중복", f"'{new_name}'은(는) 이미 사용 중인 태스크 이름입니다."); item.setText(old_name); return
                self.signals.log_message.emit(f"태스크 이름 변경: '{old_name}' -> '{new_name}'"); task.name = new_name
                if self.ui.list_widget.currentItem() == item:
                    self.ui.name_edit.blockSignals(True); self.ui.name_edit.setText(new_name); self.ui.name_edit.blockSignals(False)
                self.signals.state_changed.emit()
            new_enabled_state = (item.checkState() == Qt.Checked)
            if task.enabled != new_enabled_state:
                task.enabled = new_enabled_state; action_text = "활성화" if new_enabled_state else "비활성화"
                self.signals.log_message.emit(f"태스크 '{task.name}' {action_text}됨"); self.signals.state_changed.emit()

    @Slot(bool)
    def set_all_tasks_checked(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked; action_text = "활성화" if checked else "비활성화"
        self.ui.list_widget.blockSignals(True)
        for i in range(self.ui.list_widget.count()):
            item = self.ui.list_widget.item(i); item.setCheckState(state)
            task_id = item.data(Qt.UserRole)
            if task_id in self.data: self.data[task_id].enabled = checked
        self.ui.list_widget.blockSignals(False)
        self.signals.log_message.emit(f"모든 태스크를 {action_text}했습니다."); self.signals.state_changed.emit()

    @Slot(QListWidgetItem, QListWidgetItem)
    def on_task_selected(self, current, previous):
        self.is_loading = True
        is_item_selected = current is not None
        for btn in [self.ui.remove_btn, self.ui.copy_btn, self.ui.up_btn, self.ui.down_btn]: btn.setEnabled(is_item_selected)
        self.ui.name_edit.setEnabled(is_item_selected)
        self.ui.prompt_edit.setEnabled(is_item_selected)
        self.ui.output_template_edit.setEnabled(is_item_selected)
        if not current:
            self.ui.name_edit.clear(); self.ui.prompt_edit.clear(); self.ui.output_template_edit.clear()
        else:
            task_id = current.data(Qt.UserRole)
            if task_id in self.data:
                task = self.data[task_id]
                self.ui.name_edit.setText(task.name)
                self.ui.prompt_edit.setPlainText(task.prompt)
                self.ui.output_template_edit.setPlainText(task.output_template)
        self.is_loading = False