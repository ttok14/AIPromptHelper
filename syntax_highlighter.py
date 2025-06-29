# syntax_highlighter.py

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont

class VariableSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._valid_variables = set()

        self.valid_format = QTextCharFormat()
        self.valid_format.setForeground(QColor("#4a90e2"))
        self.valid_format.setFontWeight(QFont.Bold)
        
        self.invalid_format = QTextCharFormat()
        self.invalid_format.setUnderlineColor(Qt.red)
        self.invalid_format.setUnderlineStyle(QTextCharFormat.WaveUnderline)

        self.pattern = QRegularExpression(r"\{([^}]+)\}")

    def set_valid_variables(self, var_set):
        self._valid_variables = var_set
        self.rehighlight()

    def highlightBlock(self, text):
        # *** 수정됨: globalIterator -> globalMatch ***
        iterator = self.pattern.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            var_name = match.captured(1)
            
            if var_name in self._valid_variables:
                self.setFormat(match.capturedStart(), match.capturedLength(), self.valid_format)
            else:
                self.setFormat(match.capturedStart(), match.capturedLength(), self.invalid_format)