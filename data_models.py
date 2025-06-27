# data_models.py

import uuid

class Variable:
    def __init__(self, name="새 변수", value="", id=None):
        self.id = id if id else str(uuid.uuid4())
        self.name = name
        self.value = value

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'value': self.value
        }

    def __repr__(self):
        return f"Variable(id={self.id}, name='{self.name}')"

class Task:
    def __init__(self, name="새 태스크", prompt="", id=None):
        self.id = id if id else str(uuid.uuid4())
        self.name = name
        self.prompt = prompt
        
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'prompt': self.prompt
        }
        
    def copy(self):
        """태스크 복사본 생성"""
        return Task(name=f"{self.name} (복사본)", prompt=self.prompt)

    def __repr__(self):
        return f"Task(id={self.id}, name='{self.name}')"