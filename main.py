import os
import ctypes
import subprocess
import psutil
import glob
from fastapi import FastAPI, HTTPException, Cookie, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PASSWORD_FILE = os.path.join(CURRENT_DIR, "password.txt")

START_APPS_CACHE = {}

def get_stored_password():
    if not os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE, "w", encoding="utf-8") as f:
            f.write("1234")
        return "1234"
    with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

class LaunchPathRequest(BaseModel):
    path: str

class LaunchStartRequest(BaseModel):
    name: str

class AuthRequest(BaseModel):
    password: str

def check_auth(auth_token: str = Cookie(None)):
    if auth_token != get_stored_password():
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/", response_class=HTMLResponse)
async def get_interface():
    index_path = os.path.join(CURRENT_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Файл index.html не найден в папке с майн скриптом")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/auth")
async def authenticate(req: AuthRequest, response: Response):
    correct_password = get_stored_password()
    if req.password == correct_password:
        response.set_cookie(key="auth_token", value=correct_password, max_age=2592000, path="/")
        return {"status": "success"}
    raise HTTPException(status_code=401, detail="Неверный пароль")


@app.post("/api/lock")
async def lock_pc(auth_token: str = Cookie(None)):
    check_auth(auth_token)
    ctypes.windll.user32.LockWorkStation()
    return {"status": "success"}

@app.post("/api/system/shutdown")
async def shutdown_pc(req: AuthRequest, auth_token: str = Cookie(None)):
    check_auth(auth_token)
    if req.password == get_stored_password():
        os.system("shutdown /s /t 0")
        return {"status": "shutdown_initiated"}
    raise HTTPException(status_code=401, detail="Неверный пароль")

@app.post("/api/system/restart")
async def restart_pc(req: AuthRequest, auth_token: str = Cookie(None)):
    check_auth(auth_token)
    if req.password == get_stored_password():
        os.system("shutdown /r /t 0")
        return {"status": "restart_initiated"}
    raise HTTPException(status_code=401, detail="Неверный пароль")

@app.post("/api/system/sleep")
async def sleep_pc(auth_token: str = Cookie(None)):
    check_auth(auth_token)
    # Мгновенный перевод в режим сна без проверки пароля
    ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
    return {"status": "sleep_initiated"}


@app.get("/api/processes")
async def get_processes(auth_token: str = Cookie(None)):
    check_auth(auth_token)
    processes = set()
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name']
            if name and name.endswith('.exe'):
                processes.add(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
            
    return sorted(list(processes), key=lambda x: x.lower())

@app.post("/api/close/{proc_name}")
async def close_process(proc_name: str, auth_token: str = Cookie(None)):
    check_auth(auth_token)
    killed = False
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] == proc_name:
                proc.kill()
                killed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Процесс не найден")


@app.get("/api/start-apps")
async def get_start_apps(auth_token: str = Cookie(None)):
    check_auth(auth_token)
    global START_APPS_CACHE
    START_APPS_CACHE.clear()
    
    user_start = os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs")
    common_start = os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs")
    pinned_path = os.path.expandvars(r"%AppData%\Microsoft\Internet Explorer\Quick Launch\User Pinned\StartMenu")

    search_paths = [user_start, common_start, pinned_path]
    
    for path in search_paths:
        if os.path.exists(path):
            for file_path in glob.glob(os.path.join(path, "**", "*.lnk"), recursive=True):
                name = os.path.basename(file_path).replace(".lnk", "")
                
                low_name = name.lower()
                if "uninstall" not in low_name and "help" not in low_name and "readme" not in low_name:
                    START_APPS_CACHE[name] = file_path
                    
    return sorted(list(START_APPS_CACHE.keys()))

@app.post("/api/launch-start")
async def launch_from_start(req: LaunchStartRequest, auth_token: str = Cookie(None)):
    check_auth(auth_token)
    app_name = req.name
    
    if app_name in START_APPS_CACHE:
        shortcut_path = START_APPS_CACHE[app_name]
        try:
            os.startfile(shortcut_path)
            return {"status": "success"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка операционной системы: {str(e)}")
    else:
        raise HTTPException(status_code=404, detail="Программа не найдена в текущем кэше.")


@app.post("/api/launch-path")
async def launch_by_path(req: LaunchPathRequest, auth_token: str = Cookie(None)):
    check_auth(auth_token)
    clean_path = req.path.strip('"')
    if os.path.exists(clean_path):
        try:
            os.startfile(clean_path)
            return {"status": "success"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=404, detail="Файл по указанному пути не найден")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)