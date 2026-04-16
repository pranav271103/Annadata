import os

def fix_file(path):
    with open(path, 'rb') as f:
        content = f.read()
    
    # Try to decode as utf-8 (might fail)
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        # If it fails, it was likely corrupted by PS Set-Content (ANSI)
        text = content.decode('latin-1')
    
    # Replace common suspects
    text = text.replace('', '-')
    text = text.replace('Â', '') # often comes with CP1252 to UTF8 mess
    text = text.replace('—', '-')
    text = text.replace('×', 'x')
    
    # Final check: remove anything non-ascii for safety since we're in a crash loop
    # We'll just keep it simple and write as utf-8
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"Fixed {path}")

fix_file(r'services\kisaan_sahayak\app.py')
fix_file(r'services\kisaan_sahayak\data.py')
