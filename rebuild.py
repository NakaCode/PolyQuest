"""
Script de build do PolyQuest.
Contorna o problema de encoding do 'Á' em "Área de Trabalho" ao chamar PyInstaller via PowerShell/cmd.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = sys.executable
ISCC = r"C:\Users\zangp\AppData\Local\Programs\Inno Setup 6\ISCC.exe"

steps = [
    # 1. Matar exe em execução (ignora erro se não estiver rodando)
    ["taskkill", "/f", "/im", "PolyQuest.exe"],
    # 2. PyInstaller
    [PYTHON, "-m", "PyInstaller", "PolyQuest.spec", "--noconfirm"],
]

for cmd in steps:
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0 and "taskkill" not in cmd[0]:
        print(f"[ERRO] Passo falhou com código {result.returncode}")
        sys.exit(result.returncode)

# 3. Copiar arquivos para dist/
import shutil
for fname in ["config.json", "icon.ico", "icon_settings.ico"]:
    src = ROOT / fname
    dst = ROOT / "dist" / fname
    if src.exists():
        shutil.copy2(src, dst)
        print(f"[OK] Copiado: {fname} -> dist/")
    else:
        print(f"[AVISO] {fname} não encontrado, pulando.")

# 4. Inno Setup
print(f"\n>>> {ISCC} PolyQuest.iss")
result = subprocess.run([ISCC, "PolyQuest.iss"], cwd=str(ROOT))
if result.returncode != 0:
    print(f"[ERRO] Inno Setup falhou com código {result.returncode}")
    sys.exit(result.returncode)

print("\n[BUILD CONCLUÍDO] PolyQuest_Setup.exe gerado com sucesso.")
