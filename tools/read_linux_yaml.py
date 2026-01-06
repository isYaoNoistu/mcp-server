# -*- coding: utf-8 -*-
import os

FILE_PATH = r"D:\mcp-server\README.md"

class ReadFilesTool:
    name = "read_file"
    description = "Read Files"
    input_schema = {
        "type": "object",
        "properties": {},
        "required": []
    }

    def run(self, params):
        if not os.path.isfile(FILE_PATH):
            return f"File not found: {FILE_PATH}"
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            return f.read()


tool = ReadFilesTool()
