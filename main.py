import os
import re
import json
import subprocess
import sys
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

import google.generativeai as genai
from groq import Groq

# 1. Load API Keys
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Konstanta Folder & File
SAVE_DIR = "generated_code"
HISTORY_FILE = "chat_history.json"
os.makedirs(SAVE_DIR, exist_ok=True)

# --- KELAS UNTUK REQUEST DATA ---
class ChatRequest(BaseModel):
    message: str
    model_choice: str = "groq"

class RunCodeRequest(BaseModel):
    filename: str

class RawCodeRequest(BaseModel):
    code: str

# --- FUNGSI MEMORI (INGATAN) ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)

# --- ENDPOINT UTAMA (WEB UI) ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

# --- ENDPOINT MEMORI ---
@app.get("/api/history")
async def get_history():
    return {"history": load_history()}

@app.post("/api/clear")
async def clear_history():
    save_history([])
    return {"status": "cleared"}

# --- ENDPOINT CODE RUNNER (JALANKAN FILE) ---
@app.post("/api/run")
async def run_code(request: RunCodeRequest):
    filepath = os.path.join(SAVE_DIR, request.filename)
    if not os.path.exists(filepath):
        return {"error": "File tidak ditemukan di folder generated_code."}
    
    try:
        result = subprocess.run(
            [sys.executable, filepath], 
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        if not output.strip():
            output = "(Kode berjalan sukses, tapi tidak ada output di terminal.)"
        return {"output": output}
    except subprocess.TimeoutExpired:
        return {"error": "Waktu eksekusi habis (lebih dari 5 detik)."}
    except Exception as e:
        return {"error": str(e)}

# --- ENDPOINT CODE RUNNER (JALANKAN KODE MENTAH DARI CHAT) ---
@app.post("/api/run_raw")
async def run_raw_code(request: RawCodeRequest):
    temp_file = os.path.join(SAVE_DIR, "temp_execution.py")
    try:
        with open(temp_file, "w") as f:
            f.write(request.code)
        
        result = subprocess.run(
            [sys.executable, temp_file], 
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        if not output.strip():
            output = "(Kode berjalan sukses, tanpa output.)"
        
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        return {"output": output}
    except subprocess.TimeoutExpired:
        if os.path.exists(temp_file): os.remove(temp_file)
        return {"error": "Waktu habis (lebih dari 5 detik)."}
    except Exception as e:
        if os.path.exists(temp_file): os.remove(temp_file)
        return {"error": str(e)}

# --- FUNGSI PENYIMPAN FILE OTOMATIS ---
def process_ai_response(text):
    pattern = r"\[SAVE_FILE:\s*(.*?)\]\s*```(?:\w+)?\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    
    saved_files = []
    for filename, code_content in matches:
        filepath = os.path.join(SAVE_DIR, filename.strip())
        try:
            with open(filepath, "w") as f:
                f.write(code_content)
            saved_files.append(filename.strip())
        except Exception as e:
            print(f"Gagal menyimpan file: {e}")
            
    clean_text = re.sub(r"\[SAVE_FILE:\s*.*?\]\s*", "", text)
    if saved_files:
        notif = f"\n\n✅ **(Sistem: File {', '.join(saved_files)} tersimpan di laptop. Kamu bisa klik tombol 'Jalankan' di kotak kode!)**"
        return clean_text + notif
    return clean_text

# --- ENDPOINT CHAT UTAMA (AI & LOGIKA) ---
@app.post("/api/chat")
async def chat_with_agent(request: ChatRequest):
    try:
        system_prompt = """Kamu adalah "Teman", seorang AI Agent expert software engineering. 
        Gunakan bahasa Indonesia yang santai tapi profesional.
        [ATURAN MEMBUAT FILE]:
        Jika user meminta untuk "membuatkan file", WAJIB balas dengan format:
        [SAVE_FILE: nama_file.py]
        ```python
        # isi kode di sini
        ```"""

        # 1. Ambil memori sebelumnya
        history = load_history()
        
        # 2. Simpan pesan user yang baru ke memori
        history.append({"role": "user", "content": request.message})
        
        # Batasi memori maksimal 10 pesan terakhir agar tidak kena limit token API
        if len(history) > 10:
            history = history[-10:]

        response_text = ""

        # 3. Panggil AI (Gemini atau Groq)
        if request.model_choice == "gemini":
            try:
                model = genai.GenerativeModel(model_name='gemini-2.5-flash', system_instruction=system_prompt)
                gemini_history = [{"role": "user" if msg["role"]=="user" else "model", "parts": [msg["content"]]} for msg in history]
                response = model.generate_content(gemini_history)
                response_text = response.text
            except Exception:
                chat_completion = groq_client.chat.completions.create(
                    messages=[{"role": "system", "content": system_prompt}] + history,
                    model="openai/gpt-oss-120b", temperature=0.5,
                )
                response_text = "⚠️ (Beralih ke Groq) \n\n" + chat_completion.choices[0].message.content
        else:
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "system", "content": system_prompt}] + history,
                model="openai/gpt-oss-120b", temperature=0.5,
            )
            response_text = chat_completion.choices[0].message.content

        # 4. Simpan jawaban AI ke memori
        history.append({"role": "assistant", "content": response_text})
        save_history(history)

        # 5. Proses kode (jika ada) dan kembalikan respons
        final_response = process_ai_response(response_text)
        return {"reply": final_response}

    except Exception as e:
        return {"error": str(e)}
