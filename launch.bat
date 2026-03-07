@echo off
REM ═══════════════════════════════════════════════════════════
REM  Surveillance-IA — Lancement rapide
REM ═══════════════════════════════════════════════════════════

echo.
echo  ========================================
echo   Surveillance-IA - Lancement
echo  ========================================
echo.

REM Vérifier que le modèle existe
if not exist "models\finetuned\best.pt" (
    echo  [ERREUR] Modele non trouve : models\finetuned\best.pt
    echo  Telechargez best.pt depuis Colab et placez-le dans models\finetuned\
    pause
    exit /b 1
)

echo  [1] Webcam temps reel
echo  [2] Fichier video
echo  [3] Webcam + Reconnaissance Faciale
echo  [4] Enregistrer des visages
echo  [5] API REST
echo  [6] Dashboard
echo.
set /p choix="  Choix (1-6) : "

if "%choix%"=="1" (
    echo.
    echo  Lancement surveillance webcam...
    python -m src.pipeline --model models/finetuned/best.pt --source 0 --show --output outputs/webcam.mp4
)

if "%choix%"=="2" (
    set /p video="  Chemin video : "
    echo  Lancement surveillance video...
    python -m src.pipeline --model models/finetuned/best.pt --source "%video%" --show --output outputs/output.mp4
)

if "%choix%"=="3" (
    echo.
    echo  Lancement webcam avec reconnaissance faciale...
    set /p profil="  Profil (ecole/entreprise/evenement/batiment/libre) [libre] : "
    if "%profil%"=="" set profil=libre
    python -m src.pipeline --model models/finetuned/best.pt --source 0 --show --face --profil %profil% --output outputs/webcam_face.mp4
)

if "%choix%"=="4" (
    echo.
    echo  Lancement outil d'enregistrement de visages...
    python register_faces.py
)

if "%choix%"=="5" (
    echo  Lancement API REST sur http://localhost:8000 ...
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
)

if "%choix%"=="6" (
    echo  Lancement Dashboard sur http://localhost:8501 ...
    streamlit run app/dashboard.py
)

pause
