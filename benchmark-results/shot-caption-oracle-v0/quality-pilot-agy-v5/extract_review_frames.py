"""Reproduce inspection frames; ffmpeg + Pillow, no model calls."""
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent

def main():
    out = ROOT/'review'
    out.mkdir(exist_ok=True)
    for clip in json.loads((ROOT/'manifest.json').read_text())['clips']:
        q, duration = clip['query_id'], clip['duration_s']
        sheet = Image.new('RGB', (1440, 1176), 'white')
        draw = ImageDraw.Draw(sheet)
        for i in range(12):
            time = i * (duration - .1) / 11
            path = out/f'{q}_{i:02d}.jpg'
            if not path.exists():
                subprocess.run(['ffmpeg','-v','error','-ss',str(time),'-i',clip['clip_path'],'-frames:v','1','-q:v','2',str(path)], check=True)
            im = Image.open(path)
            im.thumbnail((480,270))
            x,y = i%3*480, i//3*294
            sheet.paste(im,(x,y))
            draw.text((x,y+270),f'{q} {time:.2f}s',fill='black')
        if not (out/f'{q}_sheet.jpg').exists():
            sheet.save(out/f'{q}_sheet.jpg')

if __name__ == '__main__':
    main()
