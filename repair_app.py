import os

def fix_file(path):
    with open(path, 'rb') as f:
        content = f.read()
    
    try:
        text = content.decode('utf-16')
        print(f"Decoded {path} as UTF-16")
    except:
        text = content.decode('latin-1')
        print(f"Decoded {path} as Latin-1")
    
    if '-i-m-p-o-r-t-' in text or '-F-A-S-T-A-P-I-' in text:
        text = text.replace('-', '')
    
    # Also clean up any BOM if present or weird chars
    text = text.strip()
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"Fixed {path}")

fix_file(r'services\kisaan_sahayak\app.py')
