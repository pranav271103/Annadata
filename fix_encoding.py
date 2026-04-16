import os

def fix_encoding(filepath):
    try:
        # Try reading as UTF-16
        with open(filepath, 'rb') as f:
            content = f.read()
        
        # Check if it looks like UTF-16 (contains null bytes or BOM)
        # Or just try common agricultural encodings...
        for enc in ['utf-16', 'utf-16-le', 'utf-16-be', 'utf-8', 'latin-1']:
            try:
                text = content.decode(enc)
                if 'import' in text or 'def' in text or 'class' in text:
                    print(f"Detected {enc} for {filepath}")
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(text)
                    return True
            except:
                continue
        return False
    except Exception as e:
        print(f"Error fixing {filepath}: {e}")
        return False

if __name__ == "__main__":
    fix_encoding(r'c:\Users\prana\Downloads\Annadata\Annadata\services\kisaan_sahayak\app.py')
