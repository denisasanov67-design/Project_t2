# fix_imports.py
import os
import re

app_dir = "app"
files_to_fix = {
    "models.py": [
        (r"^from database import", r"from app.database import"),
    ],
    "auth.py": [
        (r"^import models", r"from app import models"),
        (r"^from database import", r"from app.database import"),
    ],
    "crud.py": [
        (r"^import models", r"from app import models"),
        (r"^import schemas", r"from app import schemas"),
    ],
    "main.py": [
        (r"^import models, schemas, auth, crud", r"from app import models, schemas, auth, crud"),
        (r"^from database import", r"from app.database import"),
    ]
}

for filename, replacements in files_to_fix.items():
    filepath = os.path.join(app_dir, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Исправлен {filepath}")
        else:
            print(f"- {filepath} не требует исправлений")
    else:
        print(f"✗ {filepath} не найден")

print("\nГотово! Запустите тест снова: python test_imports.py")