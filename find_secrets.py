import os
import re

def find_long_strings(directory):
    pattern = re.compile(r'[a-zA-Z0-9_-]{32,}')
    for root, dirs, files in os.walk(directory):
        if '.git' in dirs:
            dirs.remove('.git')
        if 'venv' in dirs:
            dirs.remove('venv')
            
        for file in files:
            if file.endswith(('.py', '.html', '.css', '.js', '.md', '.txt', '.yaml', '.yml')):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        matches = pattern.findall(content)
                        if matches:
                            print(f"\nIn {path}:")
                            for match in matches:
                                print(f"  - {match}")
                except Exception as e:
                    pass

if __name__ == "__main__":
    find_long_strings('.')
