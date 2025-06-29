# data_models.py

import uuid

class Variable:
    def __init__(self, name="새 변수", value="", id=None):
        self.id = id if id else str(uuid.uuid4())
        self.name = name
        self.value = value

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'value': self.value}

    def __repr__(self):
        return f"Variable(id={self.id}, name='{self.name}')"

class Task:
    # *** 수정됨: output_template 필드 추가 ***
    def __init__(self, name="새 태스크", prompt="", output_template="", id=None, enabled=True):
        self.id = id if id else str(uuid.uuid4())
        self.name = name
        self.prompt = prompt
        self.output_template = output_template
        self.enabled = enabled

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'prompt': self.prompt,
            'output_template': self.output_template,
            'enabled': self.enabled
        }
        
    def __repr__(self):
        return f"Task(id={self.id}, name='{self.name}', enabled={self.enabled})"