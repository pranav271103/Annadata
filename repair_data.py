import os

DATA_PATH = r'services\kisaan_sahayak\data.py'

with open(DATA_PATH, 'rb') as f:
    content = f.read()

# Try to detect if it's UTF-16 or something similar disguised as hyphens
# Often 'abc' in UTF-16LE looks like 'a\x00b\x00c\x00'
# My view showed '-a-b-c-' which is weird.

try:
    text = content.decode('utf-16')
    print("Decoded as UTF-16")
except:
    text = content.decode('latin-1')
    print("Decoded as Latin-1")

# If it has hyphens between every char, replace them
if '-i-m-p-o-r-t-' in text:
    text = text.replace('-', '')

with open(DATA_PATH, 'w', encoding='utf-8') as f:
    f.write(text)

print("Repair complete.")
